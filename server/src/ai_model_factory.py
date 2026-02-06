import os

from langchain_openai import ChatOpenAI

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
    
    # Check if final_model is an env var key
    if final_model in [MODEL_4O_MINI, MODEL_5_MINI, MODEL_5_2]:
        env_model = os.getenv(final_model)
        if env_model:
            final_model = env_model
    
    # Map constants to actual model names if they aren't env vars (fallback)
    if final_model == MODEL_4O_MINI and not os.getenv(MODEL_4O_MINI):
        final_model = "gpt-4o-mini"
    elif final_model == MODEL_5_MINI and not os.getenv(MODEL_5_MINI):
        final_model = "gpt-5-mini-2025-08-07"
    elif final_model == MODEL_5_2 and not os.getenv(MODEL_5_2):
        final_model = "gpt-5.2-2025-12-11"

    return ChatOpenAI(
        model=final_model,
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=temperature
    )
