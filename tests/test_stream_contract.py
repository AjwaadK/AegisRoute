from app.schemas.generation import StreamCompleted, StreamTextDelta, TokenUsage


def test_stream_text_delta_is_plain_provider_neutral_text() -> None:
    event = StreamTextDelta(text="hello")

    assert event.text == "hello"
    assert event.model_dump() == {"text": "hello"}


def test_stream_completion_supports_observed_usage_without_sdk_types() -> None:
    event = StreamCompleted(
        provider="provider",
        model="model-v1",
        usage=TokenUsage(input_tokens=2, output_tokens=3, total_tokens=5),
    )

    assert event.usage == TokenUsage(input_tokens=2, output_tokens=3, total_tokens=5)
    assert event.__class__.__module__.startswith("app.")
    assert event.usage.__class__.__module__.startswith("app.")
