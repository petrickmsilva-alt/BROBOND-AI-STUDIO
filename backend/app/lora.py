"""LoRA dataset validation and training provider boundary."""
from dataclasses import dataclass
from uuid import UUID


@dataclass
class TrainingPlan:
    persona_id: UUID
    image_count: int
    captions: list[str]
    output_name: str


class LoRATrainer:
    minimum_images = 20
    maximum_images = 50

    def build_plan(self, persona_id: UUID, image_ids: list[UUID], identity: str, style: str) -> TrainingPlan:
        if not self.minimum_images <= len(image_ids) <= self.maximum_images:
            raise ValueError(f"LoRA training requires between {self.minimum_images} and {self.maximum_images} images")
        captions = [f"photo of {identity}, {style}, consistent identity reference {index + 1}" for index in range(len(image_ids))]
        return TrainingPlan(persona_id=persona_id, image_count=len(image_ids), captions=captions, output_name=f"persona-{persona_id}-v1.safetensors")

    def train(self, plan: TrainingPlan, output_dir: str) -> str:
        """Provider hook. A GPU worker will replace this with kohya/diffusers training."""
        raise RuntimeError("LoRA trainer is not enabled; install the training GPU profile")


lora_trainer = LoRATrainer()
