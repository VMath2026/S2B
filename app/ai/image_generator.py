import base64
import urllib.request

from app.ai.client import OpenAIConfigurationError, get_openai_client
from app.config import settings


class ImageGenerationError(RuntimeError):
    pass


def generate_bouquet_image(*, shop_name: str, state: dict) -> bytes:
    selected_flowers = state.get("selected_flowers") or []
    if not selected_flowers:
        raise ImageGenerationError("No selected flowers for image generation.")

    try:
        client = get_openai_client()
    except OpenAIConfigurationError as exc:
        raise ImageGenerationError(str(exc)) from exc

    prompt = _build_bouquet_image_prompt(shop_name=shop_name, state=state)

    try:
        response = client.images.generate(
            model=settings.openai_image_model,
            prompt=prompt,
            size=settings.openai_image_size,
            quality=settings.openai_image_quality,
            output_format=settings.openai_image_format,
            response_format="b64_json",
            n=1,
        )
    except Exception as first_exc:
        try:
            response = client.images.generate(
                model=settings.openai_image_model,
                prompt=prompt,
                size=settings.openai_image_size,
                quality=settings.openai_image_quality,
                n=1,
            )
        except Exception as second_exc:
            raise ImageGenerationError(
                f"OpenAI image request failed: {second_exc}"
            ) from first_exc

    if not response.data:
        raise ImageGenerationError("OpenAI returned an empty image response.")

    image = response.data[0]
    b64_json = getattr(image, "b64_json", None)
    if b64_json:
        return base64.b64decode(b64_json)

    image_url = getattr(image, "url", None)
    if image_url:
        with urllib.request.urlopen(image_url, timeout=30) as response_file:
            return response_file.read()

    raise ImageGenerationError("OpenAI returned an empty image response.")


def _build_bouquet_image_prompt(*, shop_name: str, state: dict) -> str:
    flowers = ", ".join(
        f"{item.get('name')} x{item.get('quantity')}"
        for item in state.get("selected_flowers") or []
    )
    colors = ", ".join(state.get("colors") or []) or "harmonious florist palette"
    style = state.get("style") or "modern elegant"
    occasion = state.get("occasion") or "flower gift"
    summary = state.get("summary") or "custom bouquet"

    return (
        "Create a realistic product preview photo of a fresh flower bouquet for a florist shop. "
        "The image should show only the bouquet, natural daylight, clean neutral background, "
        "premium floral arrangement, no people, no text, no watermark, no logo, no price tags. "
        f"Shop context: {shop_name}. "
        f"Bouquet concept: {summary}. "
        f"Occasion: {occasion}. "
        f"Style: {style}. "
        f"Requested colors: {colors}. "
        f"Flower composition: {flowers}. "
        "Make the bouquet visually balanced and plausible for the listed stems."
    )
