from abc import ABCMeta, abstractmethod
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Set, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from inference.enterprise.workflows.entities.base import GraphNone
from inference.enterprise.workflows.entities.validators import (
    is_selector,
    validate_field_has_given_type,
    validate_field_is_empty_or_selector_or_list_of_string,
    validate_field_is_in_range_zero_one_or_empty_or_selector,
    validate_field_is_list_of_selectors,
    validate_field_is_list_of_string,
    validate_field_is_one_of_selected_values,
    validate_field_is_selector_or_has_given_type,
    validate_field_is_selector_or_one_of_values,
    validate_image_biding,
    validate_image_is_valid_selector,
    validate_selector_holds_detections,
    validate_selector_holds_image,
    validate_selector_is_inference_parameter,
    validate_value_is_empty_or_number_in_range_zero_one,
    validate_value_is_empty_or_positive_number,
    validate_value_is_empty_or_selector_or_positive_number,
)
from inference.enterprise.workflows.errors import (
    ExecutionGraphError,
    InvalidStepInputDetected,
    VariableTypeError,
)


class StepInterface(GraphNone, metaclass=ABCMeta):
    @abstractmethod
    def get_input_names(self) -> Set[str]:
        """
        Supposed to give the name of all fields expected to represent inputs
        """
        pass

    @abstractmethod
    def get_output_names(self) -> Set[str]:
        """
        Supposed to give the name of all fields expected to represent outputs to be referred by other steps
        """

    @abstractmethod
    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        """
        Supposed to validate the type of input is referred
        """
        pass

    @abstractmethod
    def validate_field_binding(self, field_name: str, value: Any) -> None:
        """
        Supposed to validate the type of value that is to be bounded with field as a result of graph
        execution (values passed by client to invocation, as well as constructed during graph execution)
        """
        pass


class RoboflowModel(BaseModel, StepInterface, metaclass=ABCMeta):
    model_config = ConfigDict(protected_namespaces=())
    type: Literal["RoboflowModel"]
    name: str
    image: Union[str, List[str]]
    model_id: str
    disable_active_learning: Union[Optional[bool], str] = Field(default=False)

    @field_validator("image")
    @classmethod
    def validate_image(cls, value: Any) -> Union[str, List[str]]:
        validate_image_is_valid_selector(value=value)
        return value

    @field_validator("model_id")
    @classmethod
    def model_id_must_be_selector_or_str(cls, value: Any) -> str:
        validate_field_is_selector_or_has_given_type(
            value=value, field_name="model_id", allowed_types=[str]
        )
        return value

    @field_validator("disable_active_learning")
    @classmethod
    def disable_active_learning_must_be_selector_or_bool(
        cls, value: Any
    ) -> Union[Optional[bool], str]:
        validate_field_is_selector_or_has_given_type(
            field_name="disable_active_learning",
            allowed_types=[type(None), bool],
            value=value,
        )
        return value

    def get_type(self) -> str:
        return self.type

    def get_input_names(self) -> Set[str]:
        return {"image", "model_id", "disable_active_learning"}

    def get_output_names(self) -> Set[str]:
        return set()

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        if not is_selector(selector_or_value=getattr(self, field_name)):
            raise ExecutionGraphError(
                f"Attempted to validate selector value for field {field_name}, but field is not selector."
            )
        validate_selector_holds_image(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
        )
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"model_id", "disable_active_learning"},
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        if field_name == "image":
            validate_image_biding(value=value)
        elif field_name == "model_id":
            validate_field_has_given_type(
                field_name=field_name,
                allowed_types=[str],
                value=value,
                error=VariableTypeError,
            )
        elif field_name == "disable_active_learning":
            validate_field_has_given_type(
                field_name=field_name,
                allowed_types=[bool],
                value=value,
                error=VariableTypeError,
            )


class ClassificationModel(RoboflowModel):
    type: Literal["ClassificationModel"]
    confidence: Union[Optional[float], str] = Field(default=0.4)

    @field_validator("confidence")
    @classmethod
    def confidence_must_be_selector_or_number(
        cls, value: Any
    ) -> Union[Optional[float], str]:
        validate_field_is_in_range_zero_one_or_empty_or_selector(value=value)
        return value

    def get_input_names(self) -> Set[str]:
        inputs = super().get_input_names()
        inputs.add("confidence")
        return inputs

    def get_output_names(self) -> Set[str]:
        outputs = super().get_output_names()
        outputs.update(["predictions", "top", "confidence", "parent_id"])
        return outputs

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        super().validate_field_selector(field_name=field_name, input_step=input_step)
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"confidence"},
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        super().validate_field_binding(field_name=field_name, value=value)
        if field_name == "confidence":
            if value is None:
                raise VariableTypeError("Parameter `confidence` cannot be None")
            validate_value_is_empty_or_number_in_range_zero_one(
                value=value, error=VariableTypeError
            )


class MultiLabelClassificationModel(RoboflowModel):
    type: Literal["MultiLabelClassificationModel"]
    confidence: Union[Optional[float], str] = Field(default=0.4)

    @field_validator("confidence")
    @classmethod
    def confidence_must_be_selector_or_number(
        cls, value: Any
    ) -> Union[Optional[float], str]:
        validate_field_is_in_range_zero_one_or_empty_or_selector(value=value)
        return value

    def get_input_names(self) -> Set[str]:
        inputs = super().get_input_names()
        inputs.add("confidence")
        return inputs

    def get_output_names(self) -> Set[str]:
        outputs = super().get_output_names()
        outputs.update(["predictions", "predicted_classes", "parent_id"])
        return outputs

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        super().validate_field_selector(field_name=field_name, input_step=input_step)
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"confidence"},
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        super().validate_field_binding(field_name=field_name, value=value)
        if field_name == "confidence":
            if value is None:
                raise VariableTypeError("Parameter `confidence` cannot be None")
            validate_value_is_empty_or_number_in_range_zero_one(
                value=value, error=VariableTypeError
            )


class ObjectDetectionModel(RoboflowModel):
    type: Literal["ObjectDetectionModel"]
    class_agnostic_nms: Union[Optional[bool], str] = Field(default=False)
    class_filter: Union[Optional[List[str]], str] = Field(default=None)
    confidence: Union[Optional[float], str] = Field(default=0.4)
    iou_threshold: Union[Optional[float], str] = Field(default=0.3)
    max_detections: Union[Optional[int], str] = Field(default=300)
    max_candidates: Union[Optional[int], str] = Field(default=3000)

    @field_validator("class_agnostic_nms")
    @classmethod
    def class_agnostic_nms_must_be_selector_or_bool(
        cls, value: Any
    ) -> Union[Optional[bool], str]:
        validate_field_is_selector_or_has_given_type(
            field_name="class_agnostic_nms",
            allowed_types=[type(None), bool],
            value=value,
        )
        return value

    @field_validator("class_filter")
    @classmethod
    def class_filter_must_be_selector_or_list_of_string(
        cls, value: Any
    ) -> Union[Optional[List[str]], str]:
        validate_field_is_empty_or_selector_or_list_of_string(
            value=value, field_name="class_filter"
        )
        return value

    @field_validator("confidence", "iou_threshold")
    @classmethod
    def field_must_be_selector_or_number_from_zero_to_one(
        cls, value: Any
    ) -> Union[Optional[float], str]:
        validate_field_is_in_range_zero_one_or_empty_or_selector(
            value=value, field_name="confidence | iou_threshold"
        )
        return value

    @field_validator("max_detections", "max_candidates")
    @classmethod
    def field_must_be_selector_or_positive_number(
        cls, value: Any
    ) -> Union[Optional[int], str]:
        validate_value_is_empty_or_selector_or_positive_number(
            value=value,
            field_name="max_detections | max_candidates",
        )
        return value

    def get_input_names(self) -> Set[str]:
        inputs = super().get_input_names()
        inputs.update(
            [
                "class_agnostic_nms",
                "class_filter",
                "confidence",
                "iou_threshold",
                "max_detections",
                "max_candidates",
            ]
        )
        return inputs

    def get_output_names(self) -> Set[str]:
        outputs = super().get_output_names()
        outputs.update(["predictions", "parent_id", "image"])
        return outputs

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        super().validate_field_selector(field_name=field_name, input_step=input_step)
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={
                "class_agnostic_nms",
                "class_filter",
                "confidence",
                "iou_threshold",
                "max_detections",
                "max_candidates",
            },
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        super().validate_field_binding(field_name=field_name, value=value)
        if value is None:
            raise VariableTypeError(f"Parameter `{field_name}` cannot be None")
        if field_name == "class_agnostic_nms":
            validate_field_has_given_type(
                field_name=field_name,
                allowed_types=[bool],
                value=value,
                error=VariableTypeError,
            )
        elif field_name == "class_filter":
            if value is None:
                return None
            validate_field_is_list_of_string(
                value=value, field_name=field_name, error=VariableTypeError
            )
        elif field_name == "confidence" or field_name == "iou_threshold":
            validate_value_is_empty_or_number_in_range_zero_one(
                value=value,
                field_name=field_name,
                error=VariableTypeError,
            )
        elif field_name == "max_detections" or field_name == "max_candidates":
            validate_value_is_empty_or_positive_number(
                value=value,
                field_name=field_name,
                error=VariableTypeError,
            )


class KeypointsDetectionModel(ObjectDetectionModel):
    type: Literal["KeypointsDetectionModel"]
    keypoint_confidence: Union[Optional[float], str] = Field(default=0.0)

    @field_validator("keypoint_confidence")
    @classmethod
    def keypoint_confidence_field_must_be_selector_or_number_from_zero_to_one(
        cls, value: Any
    ) -> Union[Optional[float], str]:
        validate_field_is_in_range_zero_one_or_empty_or_selector(
            value=value, field_name="keypoint_confidence"
        )
        return value

    def get_input_names(self) -> Set[str]:
        inputs = super().get_input_names()
        inputs.add("keypoint_confidence")
        return inputs

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        super().validate_field_selector(field_name=field_name, input_step=input_step)
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"keypoint_confidence"},
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        super().validate_field_binding(field_name=field_name, value=value)
        if field_name == "keypoint_confidence":
            validate_value_is_empty_or_number_in_range_zero_one(
                value=value,
                field_name=field_name,
                error=VariableTypeError,
            )


DECODE_MODES = {"accurate", "tradeoff", "fast"}


class InstanceSegmentationModel(ObjectDetectionModel):
    type: Literal["InstanceSegmentationModel"]
    mask_decode_mode: Optional[str] = Field(default="accurate")
    tradeoff_factor: Union[Optional[float], str] = Field(default=0.0)

    @field_validator("mask_decode_mode")
    @classmethod
    def mask_decode_mode_must_be_selector_or_one_of_allowed_values(
        cls, value: Any
    ) -> Optional[str]:
        validate_field_is_selector_or_one_of_values(
            value=value,
            field_name="mask_decode_mode",
            selected_values=DECODE_MODES,
        )
        return value

    @field_validator("tradeoff_factor")
    @classmethod
    def field_must_be_selector_or_number_from_zero_to_one(
        cls, value: Any
    ) -> Union[Optional[float], str]:
        validate_field_is_in_range_zero_one_or_empty_or_selector(
            value=value, field_name="tradeoff_factor"
        )
        return value

    def get_input_names(self) -> Set[str]:
        inputs = super().get_input_names()
        inputs.update(["mask_decode_mode", "tradeoff_factor"])
        return inputs

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        super().validate_field_selector(field_name=field_name, input_step=input_step)
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"mask_decode_mode", "tradeoff_factor"},
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        super().validate_field_binding(field_name=field_name, value=value)
        if field_name == "mask_decode_mode":
            validate_field_is_one_of_selected_values(
                value=value,
                field_name=field_name,
                selected_values=DECODE_MODES,
                error=VariableTypeError,
            )
        elif field_name == "tradeoff_factor":
            validate_value_is_empty_or_number_in_range_zero_one(
                value=value,
                field_name=field_name,
                error=VariableTypeError,
            )


class OCRModel(BaseModel, StepInterface):
    type: Literal["OCRModel"]
    name: str
    image: Union[str, List[str]]

    @field_validator("image")
    @classmethod
    def image_must_only_hold_selectors(cls, value: Any) -> Union[str, List[str]]:
        validate_image_is_valid_selector(value=value)
        return value

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        if not is_selector(selector_or_value=getattr(self, field_name)):
            raise ExecutionGraphError(
                f"Attempted to validate selector value for field {field_name}, but field is not selector."
            )
        validate_selector_holds_image(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        if field_name == "image":
            validate_image_biding(value=value)

    def get_type(self) -> str:
        return self.type

    def get_input_names(self) -> Set[str]:
        return {"image"}

    def get_output_names(self) -> Set[str]:
        return {"result", "parent_id"}


class Crop(BaseModel, StepInterface):
    type: Literal["Crop"]
    name: str
    image: Union[str, List[str]]
    detections: str

    @field_validator("image")
    @classmethod
    def image_must_only_hold_selectors(cls, value: Any) -> Union[str, List[str]]:
        validate_image_is_valid_selector(value=value)
        return value

    @field_validator("detections")
    @classmethod
    def detections_must_hold_selector(cls, value: Any) -> str:
        if not is_selector(selector_or_value=value):
            raise ValueError("`detections` field can only contain selector values")
        return value

    def get_type(self) -> str:
        return self.type

    def get_input_names(self) -> Set[str]:
        return {"image", "detections"}

    def get_output_names(self) -> Set[str]:
        return {"crops", "parent_id"}

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        if not is_selector(selector_or_value=getattr(self, field_name)):
            raise ExecutionGraphError(
                f"Attempted to validate selector value for field {field_name}, but field is not selector."
            )
        validate_selector_holds_image(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
        )
        validate_selector_holds_detections(
            step_name=self.name,
            image_selector=self.image,
            detections_selector=self.detections,
            field_name=field_name,
            input_step=input_step,
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        if field_name == "image":
            validate_image_biding(value=value)


class Operator(Enum):
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    LOWER_THAN = "lower_than"
    GREATER_THAN = "greater_than"
    LOWER_OR_EQUAL_THAN = "lower_or_equal_than"
    GREATER_OR_EQUAL_THAN = "greater_or_equal_than"
    IN = "in"


class Condition(BaseModel, StepInterface):
    type: Literal["Condition"]
    name: str
    left: Union[float, int, bool, str, list, set]
    operator: Operator
    right: Union[float, int, bool, str, list, set]
    step_if_true: str
    step_if_false: str

    def get_type(self) -> str:
        return self.type

    def get_input_names(self) -> Set[str]:
        return {"left", "right"}

    def get_output_names(self) -> Set[str]:
        return set()

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        if not is_selector(selector_or_value=getattr(self, field_name)):
            raise ExecutionGraphError(
                f"Attempted to validate selector value for field {field_name}, but field is not selector."
            )
        input_type = input_step.get_type()
        if field_name in {"left", "right"}:
            if input_type == "InferenceImage":
                raise InvalidStepInputDetected(
                    f"Field {field_name} of step {self.type} comes from invalid input type: {input_type}. "
                    f"Expected: anything else than `InferenceImage`"
                )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        pass


class BinaryOperator(Enum):
    OR = "or"
    AND = "and"


class DetectionFilterDefinition(BaseModel):
    type: Literal["DetectionFilterDefinition"]
    field_name: str
    operator: Operator
    reference_value: Union[float, int, bool, str, list, set]


class CompoundDetectionFilterDefinition(BaseModel):
    type: Literal["CompoundDetectionFilterDefinition"]
    left: DetectionFilterDefinition
    operator: BinaryOperator
    right: DetectionFilterDefinition


class DetectionFilter(BaseModel, StepInterface):
    type: Literal["DetectionFilter"]
    name: str
    predictions: str
    filter_definition: Annotated[
        Union[DetectionFilterDefinition, CompoundDetectionFilterDefinition],
        Field(discriminator="type"),
    ]

    def get_input_names(self) -> Set[str]:
        return {"predictions"}

    def get_output_names(self) -> Set[str]:
        return {"predictions", "parent_id", "image"}

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        if not is_selector(selector_or_value=getattr(self, field_name)):
            raise ExecutionGraphError(
                f"Attempted to validate selector value for field {field_name}, but field is not selector."
            )
        validate_selector_holds_detections(
            step_name=self.name,
            image_selector=None,
            detections_selector=self.predictions,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"predictions"},
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        pass

    def get_type(self) -> str:
        return self.type


class DetectionOffset(BaseModel, StepInterface):
    type: Literal["DetectionOffset"]
    name: str
    predictions: str
    offset_x: Union[int, str]
    offset_y: Union[int, str]

    def get_input_names(self) -> Set[str]:
        return {"predictions", "offset_x", "offset_y"}

    def get_output_names(self) -> Set[str]:
        return {"predictions", "parent_id", "image"}

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        if not is_selector(selector_or_value=getattr(self, field_name)):
            raise ExecutionGraphError(
                f"Attempted to validate selector value for field {field_name}, but field is not selector."
            )
        validate_selector_holds_detections(
            step_name=self.name,
            image_selector=None,
            detections_selector=self.predictions,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"predictions"},
        )
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"offset_x", "offset_y"},
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        if field_name in {"offset_x", "offset_y"}:
            validate_field_has_given_type(
                field_name=field_name,
                value=value,
                allowed_types=[int],
                error=VariableTypeError,
            )

    def get_type(self) -> str:
        return self.type


class AbsoluteStaticCrop(BaseModel, StepInterface):
    type: Literal["AbsoluteStaticCrop"]
    name: str
    image: Union[str, List[str]]
    x_center: Union[int, str]
    y_center: Union[int, str]
    width: Union[int, str]
    height: Union[int, str]

    @field_validator("image")
    @classmethod
    def image_must_only_hold_selectors(cls, value: Any) -> Union[str, List[str]]:
        validate_image_is_valid_selector(value=value)
        return value

    @field_validator("x_center", "y_center", "width", "height")
    @classmethod
    def validate_crops_coordinates(cls, value: Any) -> str:
        validate_value_is_empty_or_selector_or_positive_number(
            value=value, field_name="x_center | y_center | width | height"
        )
        return value

    def get_type(self) -> str:
        return self.type

    def get_input_names(self) -> Set[str]:
        return {"image", "x_center", "y_center", "width", "height"}

    def get_output_names(self) -> Set[str]:
        return {"crops", "parent_id"}

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        if not is_selector(selector_or_value=getattr(self, field_name)):
            raise ExecutionGraphError(
                f"Attempted to validate selector value for field {field_name}, but field is not selector."
            )
        validate_selector_holds_image(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
        )
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"x_center", "y_center", "width", "height"},
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        if field_name == "image":
            validate_image_biding(value=value)
        if field_name in {"x_center", "y_center", "width", "height"}:
            if (
                not issubclass(type(value), int) and not issubclass(type(value), float)
            ) or value != round(value):
                raise VariableTypeError(
                    f"Field {field_name} of step {self.type} must be integer"
                )


class RelativeStaticCrop(BaseModel, StepInterface):
    type: Literal["RelativeStaticCrop"]
    name: str
    image: Union[str, List[str]]
    x_center: Union[float, str]
    y_center: Union[float, str]
    width: Union[float, str]
    height: Union[float, str]

    @field_validator("image")
    @classmethod
    def image_must_only_hold_selectors(cls, value: Any) -> Union[str, List[str]]:
        validate_image_is_valid_selector(value=value)
        return value

    @field_validator("x_center", "y_center", "width", "height")
    @classmethod
    def detections_must_hold_selector(cls, value: Any) -> str:
        if issubclass(type(value), str):
            if not is_selector(selector_or_value=value):
                raise ValueError("Field must be either float of valid selector")
        elif not issubclass(type(value), float):
            raise ValueError("Field must be either float of valid selector")
        return value

    def get_type(self) -> str:
        return self.type

    def get_input_names(self) -> Set[str]:
        return {"image", "x_center", "y_center", "width", "height"}

    def get_output_names(self) -> Set[str]:
        return {"crops", "parent_id"}

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        if not is_selector(selector_or_value=getattr(self, field_name)):
            raise ExecutionGraphError(
                f"Attempted to validate selector value for field {field_name}, but field is not selector."
            )
        validate_selector_holds_image(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
        )
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"x_center", "y_center", "width", "height"},
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        if field_name == "image":
            validate_image_biding(value=value)
        if field_name in {"x_center", "y_center", "width", "height"}:
            validate_field_has_given_type(
                field_name=field_name,
                value=value,
                allowed_types=[float],
                error=VariableTypeError,
            )


class ClipComparison(BaseModel, StepInterface):
    type: Literal["ClipComparison"]
    name: str
    image: Union[str, List[str]]
    text: Union[str, List[str]]

    @field_validator("image")
    @classmethod
    def image_must_only_hold_selectors(cls, value: Any) -> Union[str, List[str]]:
        validate_image_is_valid_selector(value=value)
        return value

    @field_validator("text")
    @classmethod
    def text_must_be_valid(cls, value: Any) -> Union[str, List[str]]:
        if is_selector(selector_or_value=value):
            return value
        if issubclass(type(value), list):
            validate_field_is_list_of_string(value=value, field_name="text")
        elif not issubclass(type(value), str):
            raise ValueError("`text` field given must be string or list of strings")
        return value

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        if not is_selector(selector_or_value=getattr(self, field_name)):
            raise ExecutionGraphError(
                f"Attempted to validate selector value for field {field_name}, but field is not selector."
            )
        validate_selector_holds_image(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
        )
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={"text"},
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        if field_name == "image":
            validate_image_biding(value=value)
        if field_name == "text":
            if issubclass(type(value), list):
                validate_field_is_list_of_string(
                    value=value, field_name=field_name, error=VariableTypeError
                )
            elif not issubclass(type(value), str):
                validate_field_has_given_type(
                    value=value,
                    field_name=field_name,
                    allowed_types=[str],
                    error=VariableTypeError,
                )

    def get_type(self) -> str:
        return self.type

    def get_input_names(self) -> Set[str]:
        return {"image", "text"}

    def get_output_names(self) -> Set[str]:
        return {"similarity", "parent_id"}


class AggregationMode(Enum):
    AVERAGE = "average"
    MAX = "max"
    MIN = "min"


class DetectionsConsensus(BaseModel, StepInterface):
    type: Literal["DetectionsConsensus"]
    name: str
    predictions: List[str]
    required_votes: Union[int, str]
    class_aware: Union[bool, str] = Field(default=True)
    iou_threshold: Union[float, str] = Field(default=0.3)
    confidence: Union[float, str] = Field(default=0.0)
    classes_to_consider: Optional[Union[List[str], str]] = Field(default=None)
    required_objects: Optional[Union[int, Dict[str, int], str]] = Field(default=None)
    presence_confidence_aggregation: AggregationMode = Field(
        default=AggregationMode.MAX
    )
    detections_merge_confidence_aggregation: AggregationMode = Field(
        default=AggregationMode.AVERAGE
    )
    detections_merge_coordinates_aggregation: AggregationMode = Field(
        default=AggregationMode.AVERAGE
    )

    @field_validator("predictions")
    @classmethod
    def predictions_must_be_list_of_selectors(cls, value: Any) -> List[str]:
        validate_field_is_list_of_selectors(value=value, field_name="predictions")
        if len(value) < 1:
            raise ValueError(
                "There must be at least 1 `predictions` selectors in consensus step"
            )
        return value

    @field_validator("required_votes")
    @classmethod
    def required_votes_must_be_selector_or_positive_integer(
        cls, value: Any
    ) -> Union[str, int]:
        if value is None:
            raise ValueError("Field `required_votes` is required.")
        validate_value_is_empty_or_selector_or_positive_number(
            value=value, field_name="required_votes"
        )
        return value

    @field_validator("class_aware")
    @classmethod
    def class_aware_must_be_selector_or_boolean(cls, value: Any) -> Union[str, bool]:
        validate_field_is_selector_or_has_given_type(
            value=value, field_name="class_aware", allowed_types=[bool]
        )
        return value

    @field_validator("iou_threshold", "confidence")
    @classmethod
    def field_must_be_selector_or_number_from_zero_to_one(
        cls, value: Any
    ) -> Union[str, float]:
        if value is None:
            raise ValueError("Fields `iou_threshold` and `confidence` cannot be None")
        validate_field_is_in_range_zero_one_or_empty_or_selector(
            value=value, field_name="iou_threshold | confidence"
        )
        return value

    @field_validator("classes_to_consider")
    @classmethod
    def classes_to_consider_must_be_empty_or_selector_or_list_of_strings(
        cls, value: Any
    ) -> Optional[Union[str, List[str]]]:
        validate_field_is_empty_or_selector_or_list_of_string(
            value=value, field_name="classes_to_consider"
        )
        return value

    @field_validator("required_objects")
    @classmethod
    def required_objects_field_must_be_valid(
        cls, value: Any
    ) -> Optional[Union[str, int, Dict[str, int]]]:
        if value is None:
            return value
        validate_field_is_selector_or_has_given_type(
            value=value, field_name="required_objects", allowed_types=[int, dict]
        )
        if issubclass(type(value), int):
            validate_value_is_empty_or_positive_number(
                value=value, field_name="required_objects"
            )
            return value
        elif issubclass(type(value), dict):
            for k, v in value.items():
                if v is None:
                    raise ValueError(f"Field `required_objects[{k}]` must not be None.")
                validate_value_is_empty_or_positive_number(
                    value=v, field_name=f"required_objects[{k}]"
                )
        return value

    def get_input_names(self) -> Set[str]:
        return {
            "predictions",
            "required_votes",
            "class_aware",
            "iou_threshold",
            "confidence",
            "classes_to_consider",
            "required_objects",
        }

    def get_output_names(self) -> Set[str]:
        return {
            "parent_id",
            "predictions",
            "image",
            "object_present",
            "presence_confidence",
        }

    def validate_field_selector(
        self, field_name: str, input_step: GraphNone, index: Optional[int] = None
    ) -> None:
        if field_name != "predictions" and not is_selector(
            selector_or_value=getattr(self, field_name)
        ):
            raise ExecutionGraphError(
                f"Attempted to validate selector value for field {field_name}, but field is not selector."
            )
        if field_name == "predictions":
            if index is None or index > len(self.predictions):
                raise ExecutionGraphError(
                    f"Attempted to validate selector value for field {field_name}, which requires multiple inputs, "
                    f"but `index` not provided."
                )
            if not is_selector(
                selector_or_value=self.predictions[index],
            ):
                raise ExecutionGraphError(
                    f"Attempted to validate selector value for field {field_name}[{index}], but field is not selector."
                )
            validate_selector_holds_detections(
                step_name=self.name,
                image_selector=None,
                detections_selector=self.predictions[index],
                field_name=field_name,
                input_step=input_step,
                applicable_fields={"predictions"},
            )
            return None
        validate_selector_is_inference_parameter(
            step_type=self.type,
            field_name=field_name,
            input_step=input_step,
            applicable_fields={
                "required_votes",
                "class_aware",
                "iou_threshold",
                "confidence",
                "classes_to_consider",
                "required_objects",
            },
        )

    def validate_field_binding(self, field_name: str, value: Any) -> None:
        if field_name == "required_votes":
            if value is None:
                raise VariableTypeError("Field `required_votes` cannot be None.")
            validate_value_is_empty_or_positive_number(
                value=value, field_name="required_votes", error=VariableTypeError
            )
        elif field_name == "class_aware":
            validate_field_has_given_type(
                field_name=field_name,
                allowed_types=[bool],
                value=value,
                error=VariableTypeError,
            )
        elif field_name in {"iou_threshold", "confidence"}:
            if value is None:
                raise VariableTypeError(f"Fields `{field_name}` cannot be None.")
            validate_value_is_empty_or_number_in_range_zero_one(
                value=value,
                field_name=field_name,
                error=VariableTypeError,
            )
        elif field_name == "classes_to_consider":
            if value is None:
                return None
            validate_field_is_list_of_string(
                value=value,
                field_name=field_name,
                error=VariableTypeError,
            )
        elif field_name == "required_objects":
            self._validate_required_objects_binding(value=value)
            return None

    def get_type(self) -> str:
        return self.type

    def _validate_required_objects_binding(self, value: Any) -> None:
        if value is None:
            return value
        validate_field_has_given_type(
            value=value,
            field_name="required_objects",
            allowed_types=[int, dict],
            error=VariableTypeError,
        )
        if issubclass(type(value), int):
            validate_value_is_empty_or_positive_number(
                value=value,
                field_name="required_objects",
                error=VariableTypeError,
            )
            return None
        for k, v in value.items():
            if v is None:
                raise VariableTypeError(
                    f"Field `required_objects[{k}]` must not be None."
                )
            validate_value_is_empty_or_positive_number(
                value=v,
                field_name=f"required_objects[{k}]",
                error=VariableTypeError,
            )