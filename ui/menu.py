"""
Menu system for RIPTIDAL.

This module provides a menu system for the application.
"""

from typing import List, Dict, Any, Optional, Callable, Awaitable, TypeVar, Generic, Union

T = TypeVar('T')


class MenuItem(Generic[T]):
    """
    Menu item class.
    
    This class represents a menu item with a label, action, and optional data.
    """
    
    def __init__(
        self,
        label: str,
        action: Optional[Callable[..., Awaitable[T]]] = None,
        data: Any = None,
        enabled: bool = True,
        visible: bool = True
    ):
        """
        Initialize a menu item.
        
        Args:
            label: Label for the menu item
            action: Optional async function to call when the item is selected
            data: Optional data to pass to the action
            enabled: Whether the item is enabled
            visible: Whether the item is visible
        """
        self.label = label
        self.action = action
        self.data = data
        self.enabled = enabled
        self.visible = visible


class Menu:
    """
    Menu class.
    
    This class represents a menu with a title and items.
    """
    
    def __init__(self, title: str, items: Optional[List[MenuItem]] = None):
        """
        Initialize a menu.
        
        Args:
            title: Title for the menu
            items: Optional list of menu items
        """
        self.title = title
        self.items = items or []
    
    def add_item(self, item: MenuItem) -> None:
        """
        Add an item to the menu.
        
        Args:
            item: Menu item to add
        """
        self.items.append(item)
    
    def add_items(self, items: List[MenuItem]) -> None:
        """
        Add multiple items to the menu.
        
        Args:
            items: List of menu items to add
        """
        self.items.extend(items)
    
    def clear(self) -> None:
        """Clear all items from the menu."""
        self.items.clear()
    
    def get_visible_items(self) -> List[MenuItem]:
        """
        Get all visible items in the menu.
        
        Returns:
            List of visible menu items
        """
        return [item for item in self.items if item.visible]
    
    def get_enabled_items(self) -> List[MenuItem]:
        """
        Get all enabled items in the menu.
        
        Returns:
            List of enabled menu items
        """
        return [item for item in self.items if item.enabled]
    
    def get_visible_enabled_items(self) -> List[MenuItem]:
        """
        Get all visible and enabled items in the menu.
        
        Returns:
            List of visible and enabled menu items
        """
        return [item for item in self.items if item.visible and item.enabled]
    
    async def display(self, prompt: str = "Enter your choice") -> Optional[Any]:
        """
        Display the menu and get a choice from the user.
        
        Args:
            prompt: Prompt to display
            
        Returns:
            Result of the selected action, or None if no action was selected
        """
        # Get visible and enabled items
        items = self.get_visible_enabled_items()
        
        if not items:
            print("No items available")
            return None
        
        # Print the menu
        print(f"\n=== {self.title} ===")
        
        for i, item in enumerate(items):
            print(f"{i + 1}. {item.label}")
        
        print("0. Back")
        print("=" * (len(self.title) + 8))
        
        # Get the user's choice
        while True:
            try:
                choice = input(f"{prompt}: ")
                
                if not choice or choice == "0":
                    return None
                
                index = int(choice) - 1
                
                if 0 <= index < len(items):
                    item = items[index]
                    
                    if item.action:
                        if item.data is not None:
                            return await item.action(item.data)
                        else:
                            return await item.action()
                    
                    return None
                
                print(f"Please enter a number between 0 and {len(items)}")
            except ValueError:
                print("Please enter a number")
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled")
                return None
