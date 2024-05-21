import numpy as np

from inference.core.workflows.core_steps.transformations.absolute_static_crop import (
    take_static_crop,
)
from inference.core.workflows.entities.base import (
    OriginCoordinatesSystem,
    ParentImageMetadata,
    WorkflowImageData,
)


def test_take_absolute_static_crop() -> None:
    # given
    np_image = np.zeros((100, 100, 3), dtype=np.uint8)
    np_image[50:70, 45:55] = 30  # painted the crop into (30, 30, 30)
    image = WorkflowImageData(
        parent_metadata=ParentImageMetadata(
            parent_id="origin_image",
            origin_coordinates=OriginCoordinatesSystem(
                left_top_x=0,
                left_top_y=0,
                origin_width=100,
                origin_height=100,
            ),
        ),
        numpy_image=np_image,
    )

    # when
    result = take_static_crop(
        image=image,
        x_center=50,
        y_center=60,
        width=10,
        height=20,
    )

    # then
    assert (
        result.numpy_image == (np.ones((20, 10, 3), dtype=np.uint8) * 30)
    ).all(), "Crop must have the exact size and color"
    assert result.parent_metadata.parent_id.startswith(
        "absolute_static_crop."
    ), "Parent must be set at crop step identifier"
    assert result.parent_metadata.origin_coordinates == OriginCoordinatesSystem(
        left_top_x=45,
        left_top_y=50,
        origin_width=100,
        origin_height=100,
    ), "Origin coordinates of crop and image size metadata must be maintained through the operation"
    assert (
        result.workflow_root_ancestor_metadata.origin_coordinates
        == OriginCoordinatesSystem(
            left_top_x=45,
            left_top_y=50,
            origin_width=100,
            origin_height=100,
        )
    ), "Root Origin coordinates of crop and image size metadata must be maintained through the operation"
