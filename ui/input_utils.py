"""
Utility functions for handling user input in the CLI.
"""
from typing import List, Optional, Any

async def get_input(prompt: str, default: Optional[str] = None) -> str:
    """
    Get input from the user.
    
    Args:
        prompt: Prompt to display
        default: Default value
        
    Returns:
        User input
    """
    if default:
        prompt_display = f"{prompt} [{default}]: "
    else:
        prompt_display = f"{prompt}: "
    
    try:
        value = input(prompt_display)
        if not value and default:
            return default
        return value
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled")
        return ""

async def get_choice(prompt: str, choices: List[Any], display_choices: bool = True, default: Optional[int] = None) -> int:
    """
    Get a choice from the user from a list of items.
    
    Args:
        prompt: Prompt to display.
        choices: List of items to choose from. Can be strings or objects with a 'name' or 'label' attribute.
        display_choices: Whether to print the list of choices.
        default: Default choice index (0-based). If provided, this will be used when the user enters nothing.
            
    Returns:
        Index of the chosen item, or -1 if cancelled or invalid.
    """
    if display_choices:
        print("Available options:")
        for i, choice_item in enumerate(choices):
            label = getattr(choice_item, 'label', getattr(choice_item, 'name', str(choice_item)))
            print(f"{i+1}. {label}")
    
    # Prepare prompt with default if provided
    display_prompt = prompt
    if default is not None:
        # For display, convert 0-based index to 1-based
        display_default = default + 1 if display_choices else default
        display_prompt = f"{prompt} [{display_default}]"
    
    while True:
        try:
            value_str = await get_input(display_prompt)
            if not value_str:
                # Return default if provided, otherwise -1
                return default if default is not None else -1
            
            value_int = int(value_str)
            
            if 0 <= value_int < len(choices): # Assumes 0-indexed input if not displayed 1-based
                 return value_int
            elif 1 <= value_int <= len(choices): # Assumes 1-indexed input if displayed
                 return value_int -1

            print(f"Please enter a number between {1 if display_choices else 0} and {len(choices) if display_choices else len(choices)-1}.")
        except ValueError:
            print("Please enter a valid number.")
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled during choice.")
            return -1

async def get_yes_no(prompt: str, default: bool = False) -> bool:
    """
    Get a yes/no answer from the user.
    
    Args:
        prompt: Prompt to display
        default: Default value
            
    Returns:
        True for yes, False for no
    """
    default_str = "Y" if default else "N"
    while True:
        value = await get_input(f"{prompt} (Y/N)", default_str)
        if value.lower() in ["y", "yes"]:
            return True
        elif value.lower() in ["n", "no"]:
            return False
        if value == "": 
            return default
        print("Please enter Y or N.")
