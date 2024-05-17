import hashlib
import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Dict, List, Literal, Optional, Tuple, Type, Union
from uuid import uuid4

import supervision as sv
from fastapi import BackgroundTasks
from pydantic import AliasChoices, ConfigDict, Field

from inference.core.active_learning.cache_operations import (
    return_strategy_credit,
    use_credit_of_matching_strategy,
)
from inference.core.active_learning.core import prepare_image_to_registration
from inference.core.active_learning.entities import (
    ImageDimensions,
    StrategyLimit,
    StrategyLimitType,
)
from inference.core.cache.base import BaseCache
from inference.core.roboflow_api import (
    get_roboflow_workspace,
    register_image_at_roboflow,
)
from inference.core.utils.image_utils import load_image
from inference.core.workflows.entities.base import OutputDefinition
from inference.core.workflows.entities.types import (
    BATCH_OF_BOOLEAN_KIND,
    BATCH_OF_INSTANCE_SEGMENTATION_PREDICTION_KIND,
    BATCH_OF_KEYPOINT_DETECTION_PREDICTION_KIND,
    BATCH_OF_OBJECT_DETECTION_PREDICTION_KIND,
    BATCH_OF_STRING_KIND,
    BOOLEAN_KIND,
    ROBOFLOW_PROJECT_KIND,
    STRING_KIND,
    FlowControl,
    StepOutputImageSelector,
    StepOutputSelector,
    WorkflowImageSelector,
    WorkflowParameterSelector,
)
from inference.core.workflows.prototypes.block import (
    WorkflowBlock,
    WorkflowBlockManifest,
)

SHORT_DESCRIPTION = "TODO"

LONG_DESCRIPTION = """
"""

WORKSPACE_NAME_CACHE_EXPIRE = 900  # 15 min
TIMESTAMP_FORMAT = "%Y_%m_%d"
DUPLICATED_STATUS = "Duplicated image"
BatchCreationFrequency = Literal["never", "daily", "weekly", "monthly"]


class BlockManifest(WorkflowBlockManifest):
    model_config = ConfigDict(
        json_schema_extra={
            "short_description": SHORT_DESCRIPTION,
            "long_description": LONG_DESCRIPTION,
            "license": "Apache-2.0",
            "block_type": "sink",
        }
    )
    type: Literal["RoboflowDataCollector"]
    images: Union[WorkflowImageSelector, StepOutputImageSelector] = Field(
        description="Reference at image to be used as input for step processing",
        examples=["$inputs.image", "$steps.cropping.crops"],
        validation_alias=AliasChoices("images", "image"),
    )
    predictions: Optional[
        StepOutputSelector(
            kind=[
                BATCH_OF_OBJECT_DETECTION_PREDICTION_KIND,
                BATCH_OF_INSTANCE_SEGMENTATION_PREDICTION_KIND,
                BATCH_OF_KEYPOINT_DETECTION_PREDICTION_KIND,
            ]
        )
    ] = Field(
        default=None,
        description="Reference to detection-like predictions",
        examples=["$steps.object_detection_model.predictions"],
    )
    target_project: Union[
        WorkflowParameterSelector(kind=[ROBOFLOW_PROJECT_KIND]), str
    ] = Field(
        description="name of Roboflow dataset / project to be used as target for collected data",
        examples=["my_dataset", "$inputs.target_al_dataset"],
    )
    usage_quota_name: str = Field(
        description="Unique name for Roboflow project pointed by `target_project` parameter, that identifies "
        "usage quota applied for this block.",
        examples=["quota-for-data-sampling-1"],
    )
    minutely_usage_limit: int = Field(
        default=10,
        description="Maximum number of data registration requests per minute accounted in scope of "
        "single server or whole Roboflow platform, depending on context of usage.",
        examples=[10, 60],
    )
    hourly_usage_limit: int = Field(
        default=100,
        description="Maximum number of data registration requests per hour accounted in scope of "
        "single server or whole Roboflow platform, depending on context of usage.",
        examples=[10, 60],
    )
    daily_usage_limit: int = Field(
        default=1000,
        description="Maximum number of data registration requests per day accounted in scope of "
        "single server or whole Roboflow platform, depending on context of usage.",
        examples=[10, 60],
    )
    max_image_size: Tuple[int, int] = Field(
        default=(512, 512),
        description="Maximum size of the image to be registered - bigger images will be "
        "downsized preserving aspect ratio. Format of data: `(width, height)`",
        examples=[(512, 512), (1920, 1080)],
    )
    compression_level: int = Field(
        default=75,
        gt=0,
        le=100,
        description="Compression level for images registered",
        examples=[75],
    )
    registration_tags: List[
        Union[WorkflowParameterSelector(kind=[STRING_KIND]), str]
    ] = Field(
        default_factory=lambda: [],
        description="Tags to be attached to registered datapoints",
        examples=[["location-florida", "factory-name", "$inputs.dynamic_tag"]],
    )
    disable_sink: Union[bool, WorkflowParameterSelector(kind=[BOOLEAN_KIND])] = Field(
        default=False,
        description="boolean flag that can be also reference to input - to arbitrarily disable "
        "data collection for specific request",
        examples=[True, "$inputs.disable_active_learning"],
    )
    fire_and_forget: Union[bool, WorkflowParameterSelector(kind=[BOOLEAN_KIND])] = (
        Field(
            default=True,
            description="Boolean flag dictating if sink is supposed to be executed in the background, "
            "not waiting on status of registration before end of workflow run. Use `True` if best-effort "
            "registration is needed, use `False` while debugging and if error handling is needed",
        )
    )
    labeling_batch_prefix: str = Field(
        default="workflows_data_collector",
        description="Prefix of the name for labeling batches that will be registered in Roboflow app",
        examples=["my_labeling_batch_name"],
    )
    labeling_batches_recreation_frequency: BatchCreationFrequency = Field(
        default="never",
        description="Frequency in which new labeling batches are created in Roboflow app. New batches "
        "are created with name prefix provided in `labeling_batch_prefix` in given time intervals."
        "Useful in organising labeling flow.",
        examples=["never", "daily"],
    )

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return [
            OutputDefinition(name="error_status", kind=[BATCH_OF_BOOLEAN_KIND]),
            OutputDefinition(name="message", kind=[BATCH_OF_STRING_KIND]),
        ]


class RoboflowDataCollectorBlock(WorkflowBlock):

    def __init__(
        self,
        cache: BaseCache,
        background_tasks: Optional[BackgroundTasks],
        api_key: Optional[str],
    ):
        self._cache = cache
        self._background_tasks = background_tasks
        self._api_key = api_key

    @classmethod
    def get_init_parameters(cls) -> List[str]:
        return ["cache", "background_tasks", "api_key"]

    @classmethod
    def get_manifest(cls) -> Type[WorkflowBlockManifest]:
        return BlockManifest

    async def run_locally(
        self,
        images: List[Optional[dict]],
        predictions: Optional[List[Optional[sv.Detections]]],
        target_project: str,
        usage_quota_name: str,
        minutely_usage_limit: int,
        hourly_usage_limit: int,
        daily_usage_limit: int,
        max_image_size: Tuple[int, int],
        compression_level: int,
        registration_tags: List[str],
        disable_sink: bool,
        fire_and_forget: bool,
        labeling_batch_prefix: str,
        labeling_batches_recreation_frequency: BatchCreationFrequency,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], FlowControl]]:
        if self._api_key is None:
            raise ValueError(
                "RoboflowDataCollector block cannot run without Roboflow API key. "
                "If you do not know how to get API key - visit "
                "https://docs.roboflow.com/api-reference/authentication#retrieve-an-api-key to learn how to "
                "retrieve one."
            )
        if disable_sink:
            return [
                {
                    "error_status": False,
                    "message": "Sink was disabled by parameter `disable_sink`",
                }
                for _ in range(len(images))
            ]
        if predictions is None:
            predictions = [None] * len(images)
        result = []
        for image, prediction in zip(images, predictions):
            error_status, message = register_datapoint_at_roboflow(
                image=image,
                prediction=prediction,
                target_project=target_project,
                usage_quota_name=usage_quota_name,
                minutely_usage_limit=minutely_usage_limit,
                hourly_usage_limit=hourly_usage_limit,
                daily_usage_limit=daily_usage_limit,
                max_image_size=max_image_size,
                compression_level=compression_level,
                registration_tags=registration_tags,
                fire_and_forget=fire_and_forget,
                labeling_batch_prefix=labeling_batch_prefix,
                new_labeling_batch_frequency=labeling_batches_recreation_frequency,
                cache=self._cache,
                background_tasks=self._background_tasks,
                api_key=self._api_key,
            )
            result.append({"error_status": error_status, "message": message})
        return result


def register_datapoint_at_roboflow(
    image: Optional[dict],
    prediction: Optional[sv.Detections],
    target_project: str,
    usage_quota_name: str,
    minutely_usage_limit: int,
    hourly_usage_limit: int,
    daily_usage_limit: int,
    max_image_size: Tuple[int, int],
    compression_level: int,
    registration_tags: List[str],
    fire_and_forget: bool,
    labeling_batch_prefix: str,
    new_labeling_batch_frequency: BatchCreationFrequency,
    cache: BaseCache,
    background_tasks: Optional[BackgroundTasks],
    api_key: str,
) -> Tuple[bool, str]:
    if image is None:
        return False, "Batch element skipped"
    registration_task = partial(
        execute_registration,
        image=image,
        prediction=prediction,
        target_project=target_project,
        usage_quota_name=usage_quota_name,
        minutely_usage_limit=minutely_usage_limit,
        hourly_usage_limit=hourly_usage_limit,
        daily_usage_limit=daily_usage_limit,
        max_image_size=max_image_size,
        compression_level=compression_level,
        registration_tags=registration_tags,
        labeling_batch_prefix=labeling_batch_prefix,
        new_labeling_batch_frequency=new_labeling_batch_frequency,
        cache=cache,
        api_key=api_key,
    )
    if fire_and_forget and background_tasks:
        background_tasks.add_task(execute_registration)
        return False, "Element registration happens in the background task"
    return registration_task()


def execute_registration(
    image: dict,
    prediction: Optional[sv.Detections],
    target_project: str,
    usage_quota_name: str,
    minutely_usage_limit: int,
    hourly_usage_limit: int,
    daily_usage_limit: int,
    max_image_size: Tuple[int, int],
    compression_level: int,
    registration_tags: List[str],
    labeling_batch_prefix: str,
    new_labeling_batch_frequency: BatchCreationFrequency,
    cache: BaseCache,
    api_key: str,
) -> Tuple[bool, str]:
    matching_strategies_limits = OrderedDict(
        {
            usage_quota_name: [
                StrategyLimit(
                    limit_type=StrategyLimitType.MINUTELY, value=minutely_usage_limit
                ),
                StrategyLimit(
                    limit_type=StrategyLimitType.HOURLY, value=hourly_usage_limit
                ),
                StrategyLimit(
                    limit_type=StrategyLimitType.DAILY, value=daily_usage_limit
                ),
            ]
        }
    )
    workspace_name = get_workspace_name(api_key=api_key, cache=cache)
    strategy_with_spare_credit = use_credit_of_matching_strategy(
        cache=cache,
        workspace=workspace_name,
        project=target_project,
        matching_strategies_limits=matching_strategies_limits,
    )
    if strategy_with_spare_credit is None:
        return False, "Registration skipped due to usage quota exceeded"
    credit_to_be_returned = False
    try:
        local_image_id = str(uuid4())
        image, is_bgr = load_image(
            value=image,
        )
        if not is_bgr:
            image = image[:, :, ::-1]
        encoded_image, scaling_factor = prepare_image_to_registration(
            image=image,
            desired_size=ImageDimensions(
                width=max_image_size[0], height=max_image_size[1]
            ),
            jpeg_compression_level=compression_level,
        )
        batch_name = generate_batch_name(
            labeling_batch_prefix=labeling_batch_prefix,
            new_labeling_batch_frequency=new_labeling_batch_frequency,
        )
        if prediction is not None:
            prediction = ...  # TODO: Adjust to scaled image
        status = register_datapoint(
            target_project=target_project,
            encoded_image=encoded_image,
            local_image_id=local_image_id,
            prediction=prediction,
            api_key=api_key,
            batch_name=batch_name,
            tags=registration_tags,
        )
        if status == DUPLICATED_STATUS:
            credit_to_be_returned = True
        return False, status
    except Exception as error:
        credit_to_be_returned = True
        logging.exception("Failed to register datapoint at Roboflow platform")
        return (
            True,
            f"Error while registration. Error type: {type(error)}. Details: {error}",
        )
    finally:
        if credit_to_be_returned:
            return_strategy_credit(
                cache=cache,
                workspace=workspace_name,
                project=target_project,
                strategy_name=strategy_with_spare_credit,
            )


def get_workspace_name(
    api_key: str,
    cache: BaseCache,
) -> str:
    api_key_hash = hashlib.md5(api_key.encode("utf-8")).hexdigest()
    cache_key = f"workflows:api_key_to_workspace:{api_key_hash}"
    cached_workspace_name = cache.get(cache_key)
    if cached_workspace_name:
        return cached_workspace_name
    workspace_name_from_api = get_roboflow_workspace(api_key=api_key)
    cache.set(
        key=cache_key, value=workspace_name_from_api, expire=WORKSPACE_NAME_CACHE_EXPIRE
    )


def generate_batch_name(
    labeling_batch_prefix: str,
    new_labeling_batch_frequency: BatchCreationFrequency,
) -> str:
    if new_labeling_batch_frequency == "never":
        return labeling_batch_prefix
    timestamp_generator = RECREATION_INTERVAL2TIMESTAMP_GENERATOR[
        new_labeling_batch_frequency
    ]
    timestamp = timestamp_generator()
    return f"{labeling_batch_prefix}_{timestamp}"


def generate_today_timestamp() -> str:
    return datetime.today().strftime(TIMESTAMP_FORMAT)


def generate_start_timestamp_for_this_week() -> str:
    today = datetime.today()
    return (today - timedelta(days=today.weekday())).strftime(TIMESTAMP_FORMAT)


def generate_start_timestamp_for_this_month() -> str:
    return datetime.today().replace(day=1).strftime(TIMESTAMP_FORMAT)


RECREATION_INTERVAL2TIMESTAMP_GENERATOR = {
    "daily": generate_today_timestamp,
    "weekly": generate_start_timestamp_for_this_week,
    "monthly": generate_start_timestamp_for_this_month,
}


def register_datapoint(
    target_project: str,
    encoded_image: bytes,
    local_image_id: str,
    prediction: Optional[sv.Detections],
    api_key: str,
    batch_name: str,
    tags: List[str],
) -> str:
    roboflow_image_id = safe_register_image_at_roboflow(
        target_project=target_project,
        encoded_image=encoded_image,
        local_image_id=local_image_id,
        api_key=api_key,
        batch_name=batch_name,
        tags=tags,
    )
    if roboflow_image_id is None:
        return DUPLICATED_STATUS
    if prediction is None:
        return "Successfully registered image"
    # TODO: part for saving prediction


def safe_register_image_at_roboflow(
    target_project: str,
    encoded_image: bytes,
    local_image_id: str,
    api_key: str,
    batch_name: str,
    tags: List[str],
) -> Optional[str]:
    registration_response = register_image_at_roboflow(
        api_key=api_key,
        dataset_id=target_project,
        local_image_id=local_image_id,
        image_bytes=encoded_image,
        batch_name=batch_name,
        tags=tags,
    )
    image_duplicated = registration_response.get("duplicate", False)
    if image_duplicated:
        logging.warning(f"Image duplication detected: {registration_response}.")
        return None
    return registration_response["id"]
