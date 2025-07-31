from semantic_kernel.kernel_pydantic import KernelBaseModel

from sk_agents.ska_types import EmbeddedImage


class ButtonGuess(KernelBaseModel):
    guess: int
    embedded_image: EmbeddedImage
