from semantic_kernel.kernel_pydantic import KernelBaseModel


class NumbersInput(KernelBaseModel):
    number_1: int
    number_2: int
    number_3: int


class MathOutput(KernelBaseModel):
    result: int
