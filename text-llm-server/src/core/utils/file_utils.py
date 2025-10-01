from pathlib import Path
from functools import lru_cache
import json

@lru_cache(maxsize=1)
def _load_config(config_path : str ="prompts/config.json") -> dict:
    """
    Load and cache the config file to validate types.
    Across subsequent calls, the same path returns the same cached result.

    Args:
        config_path (str): Valid path to the JSON prompts config json. default="prompts/config.json"
    Returns:
        dict: dictionary of config data
    """
    config_path = Path(__file__).parent.parent / Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Could not find prompts config file {config_path}")

    with config_path.open(encoding="utf-8") as f:
        return json.load(f)

def validate_types(prompt_type: str, category_type: str, config_path: str="prompts/config.json") -> None:
    """
    Validate if prompt type and category type exist
    
    Args:
        prompt_type (str): type of prompt you want to validate.
        category_type (str): type of category to validate.
        config_path (str): valid path to the JSON prompts config json. default="prompts/config.json"
    
    Returns:
        None: If prompt types are validated returns None. Otherwise raises an error
    """
    if not prompt_type or not category_type:
        raise ValueError("prompt_type or category_type cannot be empty")

    config_data = _load_config(config_path)
    valid_prompt_types = config_data["prompt_types"]
    valid_category_types = config_data["category_types"]

    if prompt_type not in valid_prompt_types:
        raise ValueError(
            f"Invalid prompt type '{prompt_type}'"
            f"Valid options: {valid_prompt_types}"
        )
    elif category_type not in valid_category_types:
        raise ValueError(
            f"Invalid category_type '{category_type}'"
            f"Valid options: {valid_category_types}"
        )

@lru_cache(maxsize=32)
def load_file(
    prompt_type: str, 
    category_type: str, 
    config_path: str="prompts/config.json",
    prompts_dir:str="prompts") -> str:
    """
    Load and cache prompt file contents 
    Across subsequent calls, the same path returns the same cached result.

    Args:
        prompt_type (str): type of prompt you want to validate.
        category_type (str): type of category to validate.
        config_path (str): valid path to the JSON prompts config json. default="prompts/config.json"
        prompts_dir (str): path to main prompts dir. default="prompts"

    """
    validate_types(prompt_type=prompt_type, category_type=category_type, config_path=config_path)
    file_path = Path(__file__).parent.parent / Path(prompts_dir) / prompt_type / f"{category_type}.md"

    if not file_path.exists():
        raise FileNotFoundError(
            f"Missing {category_type}.md for {prompt_type}"
        )
    
    return file_path.read_text(encoding="utf-8").strip()
