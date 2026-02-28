import os

from langchain_openai import ChatOpenAI
from src.config import settings

# Model Constants
MODEL_4O_MINI = "MODEL_4O_MINI"
MODEL_5_MINI = "MODEL_5_MINI"
MODEL_5_2 = "MODEL_5_2"
MODEL_4O = "gpt-4o"

def get_model(model_name: str = MODEL_5_2, temperature: float = 0.0):
    """
    Returns a ChatOpenAI model.
    :param model_name: The name of the model to use. Defaults to MODEL_5_2.
    :param temperature: The temperature to use. Defaults to 0 for deterministic output.
    """
    # Use provided model_name
    final_model = model_name
    
    # Map constants to actual model names from settings
    if final_model == MODEL_4O_MINI:
        final_model = settings.model_4o_mini
    elif final_model == MODEL_5_MINI:
        final_model = settings.model_5_mini
    elif final_model == MODEL_5_2:
        final_model = settings.model_5_2

    return ChatOpenAI(
        model=final_model,
        api_key=settings.openai_api_key,
        temperature=temperature
    )
