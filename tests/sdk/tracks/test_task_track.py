from handprint.sdk.tracks import Track, TaskTrigger
from handprint.sdk.tracks.types import InputMetadata


def test_task_track_prompt_appending():
    """Test that Track with TaskTrigger correctly appends missing variables prompt."""
    # Create Track with TaskTrigger and variables in content
    task_track = Track(
        name="test-task",
        content="Task with ${variable1} and ${variable2}",
        source="test.md",
        trigger=TaskTrigger(triggers=["task"]),
    )

    # Check that the prompt was appended
    expected_prompt = (
        "\n\nIf the user didn't provide any of these variables, ask the user to "
        "provide them first before the agent can proceed with the task."
    )
    assert expected_prompt in task_track.content

    # Create Track with TaskTrigger without variables but with inputs
    task_track_with_inputs = Track(
        name="test-task-inputs",
        content="Task without variables",
        source="test.md",
        trigger=TaskTrigger(triggers=["task"]),
        inputs=[InputMetadata(name="input1", description="Test input")],
    )

    # Check that the prompt was appended
    assert expected_prompt in task_track_with_inputs.content

    # Create Track with TaskTrigger without variables or inputs
    task_track_no_vars = Track(
        name="test-task-no-vars",
        content="Task without variables or inputs",
        source="test.md",
        trigger=TaskTrigger(triggers=["task"]),
    )

    # Check that the prompt was NOT appended
    assert expected_prompt not in task_track_no_vars.content
