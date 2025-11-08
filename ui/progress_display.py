"""
Manages Rich-based progress display for RIPTIDAL.
"""
from typing import Optional

from rich.console import Console, Group # Import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, DownloadColumn, TransferSpeedColumn
from rich.text import Text

from riptidal.core.download_models import DownloadProgress # Import from new location
from riptidal.utils.logger import get_logger


class RichProgressManager:
    """
    Manages Rich components for displaying download progress.
    """
    def __init__(self):
        self.logger = get_logger(__name__)

        self.track_info_text = Text(no_wrap=True)
        self.track_info_panel = Panel(self.track_info_text, title="Current Item", border_style="blue", width=80, height=8)

        self.overall_progress_display = Progress(
            TextColumn("[progress.description]{task.description}", style="bold blue", justify="left"),
            BarColumn(),
            TextColumn("{task.completed:.0f}/{task.total:.0f} items"),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            expand=True
        )
        self.overall_panel = Panel(self.overall_progress_display, title="Overall Batch", border_style="blue", padding=(1,1))

        self.album_progress_display = Progress(
            TextColumn("[progress.description]{task.description}", style="bold green", justify="left"),
            BarColumn(),
            TextColumn("{task.completed:.0f}/{task.total:.0f} items"),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            expand=True
        )
        self.album_panel = Panel(self.album_progress_display, title="Current Album", border_style="green", padding=(1,1))

        self.file_progress_display = Progress(
            TextColumn("[progress.description]{task.description}", style="bold magenta", justify="left"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            TransferSpeedColumn(),
            DownloadColumn(), 
            TimeRemainingColumn(),
            expand=True
        )
        self.file_panel = Panel(self.file_progress_display, title="Current File", border_style="magenta", padding=(1,1))
        
        self.console = Console(force_terminal=True, color_system="auto")
        self.live: Optional[Live] = None 

        self.overall_task_id: Optional[int] = None
        self.album_task_id: Optional[int] = None
        self.file_task_id: Optional[int] = None

        self._completed_tracks: int = 0
        self._total_tracks: int = 0
        
        self._album_tracks_completed: int = 0
        self._album_tracks_total: int = 0
        
        self._current_album_title_for_progress: str = ""
        self._layout_has_album_panel: bool = False

    def _create_layout_group(self, show_album_panel: bool) -> Group:
        """Constructs the layout Group based on whether the album panel should be shown."""
        renderables = [
            self.track_info_panel,
            self.overall_panel
        ]
        if show_album_panel:
            if self.album_task_id is not None:
                 self.album_progress_display.update(self.album_task_id, visible=True)
            self.album_panel.visible = True
            renderables.append(self.album_panel)
        else:
            if self.album_task_id is not None:
                 self.album_progress_display.update(self.album_task_id, visible=False)
            self.album_panel.visible = False
            
        renderables.append(self.file_panel)
        return Group(*renderables)

    def _recreate_live_if_layout_changed(self, show_album_panel: bool):
        if self.live is None or self._layout_has_album_panel != show_album_panel:
            if self.live and self.live._started:
                self.live.stop()
            
            current_layout_group = self._create_layout_group(show_album_panel=show_album_panel)
            self.live = Live(current_layout_group, console=self.console, auto_refresh=False, transient=False, vertical_overflow="crop", screen=True)
            self.live.start(refresh=True)
            self._layout_has_album_panel = show_album_panel
            self.logger.debug(f"Live display recreated. Album panel shown: {show_album_panel}")

    def set_batch_totals(self, total_tracks: int):
        """Sets the total number of original tracks for the current batch."""
        self._total_tracks = total_tracks
        self._completed_tracks = 0
        if self.overall_task_id is not None:
            self.overall_progress_display.update(self.overall_task_id, total=self._total_tracks, completed=0, visible=True, description="Overall Progress")
        else:
            if self._total_tracks > 0:
                self.overall_task_id = self.overall_progress_display.add_task(
                    "Overall Progress", total=self._total_tracks, start=True, completed=0, visible=True
                )
        self.logger.debug(f"Batch totals set: {self._total_tracks} original tracks.")


    def reset_progress_state(self):
        """Resets all progress bars and counters for a new operation."""
        self.logger.debug("Resetting Rich progress state.")
        self._completed_tracks = 0
        self._total_tracks = 0
        self._album_tracks_completed = 0
        self._album_tracks_total = 0
        self._current_album_title_for_progress = ""

        if self.overall_task_id is not None:
            self.overall_progress_display.update(self.overall_task_id, visible=False)
            self.overall_task_id = None
        if self.album_task_id is not None:
            self.album_progress_display.update(self.album_task_id, visible=False)
            self.album_task_id = None
        if self.file_task_id is not None:
            self.file_progress_display.update(self.file_task_id, visible=False)
            self.file_task_id = None
        
        self.track_info_text.plain = ""
        self._layout_has_album_panel = False
        if self.live and self.live._started:
            self.live.stop()
        self.live = None


    async def _update_rich_track_info(self, progress: DownloadProgress):
        """Helper to update the track info panel content."""
        lines = []
        if progress.is_video and progress.video_title:
            track_name_display = progress.video_title
        else:
            track_name_display = progress.track_title if progress.track_title else "Unknown Title"
        
        artist_name_display = progress.artist_names_str if progress.artist_names_str else "Unknown Artist"
        album_name_display = progress.album_title if progress.album_title else ""
        
        if progress.is_video:
            self.track_info_panel.title = "Current Video"
            lines.append(f"[bold]Video:[/] {track_name_display}")
        else:
            self.track_info_panel.title = "Current Track"
            lines.append(f"[bold]Track:[/] {track_name_display}")
        lines.append(f"[bold]Artist:[/] {artist_name_display}")
        if album_name_display:
            lines.append(f"[bold]Album:[/] {album_name_display}")
        if progress.requested_quality and progress.actual_quality:
            req_q_str = progress.requested_quality.name if hasattr(progress.requested_quality, 'name') else str(progress.requested_quality)
            act_q_str = progress.actual_quality.name if hasattr(progress.actual_quality, 'name') else str(progress.actual_quality)
            lines.append(f"[bold]Quality (Req):[/] {req_q_str}")
            lines.append(f"[bold]Quality (Act):[/] {act_q_str}")
        
        status_map = {
            "pending": "[yellow]Pending[/]",
            "downloading": "[cyan]Downloading[/]",
            "completed": "[green]Completed[/]",
            "failed": "[red]Failed[/]",
            "skipped": "[yellow]Skipped[/]"
        }
        status_str = status_map.get(progress.status, progress.status)
        lines.append(f"[bold]Status:[/] {status_str}")
        if progress.error_message:
            lines.append(f"[bold red]Error:[/] {progress.error_message}")

        new_text_content = Text.from_markup("\n".join(lines))
        
        self.track_info_panel.renderable = Text("") 
        self.track_info_panel.renderable = new_text_content

    async def update_progress(self, progress: DownloadProgress) -> None:
        """
        Update the progress display using Rich.
        
        Args:
            progress: Download progress information.
        """
        await self._update_rich_track_info(progress)

        if progress.status == "downloading":
            display_title = progress.video_title if progress.is_video and progress.video_title else progress.track_title
            display_title = display_title if display_title else "Unknown Title"
            
            if len(display_title) > 40:
                display_title = display_title[:37] + "..."
            
            file_description = f"File: {display_title}"
            if progress.is_video:
                file_description = f"Video: {display_title}"
            
            if self.file_task_id is None:
                self.file_task_id = self.file_progress_display.add_task(
                    file_description,
                    total=progress.total_bytes if progress.total_bytes is not None and progress.total_bytes > 0 else None,
                    start=True
                )
            self.file_progress_display.update(
                self.file_task_id,
                completed=progress.downloaded_bytes,
                total=progress.total_bytes if progress.total_bytes is not None and progress.total_bytes > 0 else None,
                description=file_description,
                visible=True
            )
        elif progress.status in ["completed", "failed", "skipped"]:
            if self.file_task_id is not None:
                final_total = progress.total_bytes if progress.total_bytes is not None and progress.total_bytes > 0 else progress.downloaded_bytes
                self.file_progress_display.update(self.file_task_id, completed=progress.downloaded_bytes, total=final_total, visible=False)
                self.file_task_id = None

        is_album_track_for_progress = hasattr(progress, 'is_album_track') and progress.is_album_track
        is_original_track = hasattr(progress, 'is_original') and progress.is_original

        if progress.status in ["completed", "skipped"] and (not hasattr(progress, '_counted_for_progress') or not progress._counted_for_progress):
            if is_album_track_for_progress:
                self._album_tracks_completed += 1
                if is_original_track: 
                    self._completed_tracks += 1
                    self.logger.debug(f"Original album track '{progress.track_title}' {progress.status}. Overall: {self._completed_tracks}/{self._total_tracks}. Album: {self._album_tracks_completed}/{self._album_tracks_total}")
            elif is_original_track: 
                self._completed_tracks += 1
                self.logger.debug(f"Original individual track '{progress.track_title}' {progress.status}. Overall: {self._completed_tracks}/{self._total_tracks}")
            
            setattr(progress, '_counted_for_progress', True)


        if self._total_tracks > 0:
            if self.overall_task_id is None:
                self.overall_task_id = self.overall_progress_display.add_task(
                    "Overall Progress", 
                    total=self._total_tracks, 
                    completed=self._completed_tracks,
                    visible=True
                )
            else:
                self.overall_progress_display.update(
                    self.overall_task_id, 
                    completed=self._completed_tracks, 
                    total=self._total_tracks,
                    visible=True
                )
        elif self.overall_task_id is not None: 
            self.overall_progress_display.update(self.overall_task_id, visible=False)

        
        if is_album_track_for_progress and progress.album_title and progress.total_tracks is not None:
            current_album_display_title = f"{progress.album_title} ({progress.album_index or '?'}/{progress.total_albums or '?'})"
            
            if self.album_task_id is None or self._current_album_title_for_progress != current_album_display_title:
                if self.album_task_id is not None:
                    self.album_progress_display.update(self.album_task_id, visible=False)
                
                self._current_album_title_for_progress = current_album_display_title
                # Use the initial completed count if available
                if hasattr(progress, 'album_initial_completed') and progress.album_initial_completed is not None:
                    self._album_tracks_completed = progress.album_initial_completed
                else:
                    self._album_tracks_completed = 0
                self._album_tracks_total = progress.total_tracks
                
                if progress.status in ["completed", "skipped"]: 
                     self._album_tracks_completed += 1
                
                self.album_task_id = self.album_progress_display.add_task(
                    f"Album: {current_album_display_title}",
                    total=self._album_tracks_total, 
                    completed=self._album_tracks_completed,
                    visible=True,
                    start=True
                )
            else: 
                self.album_progress_display.update(
                    self.album_task_id,
                    completed=self._album_tracks_completed,
                    total=self._album_tracks_total,
                    description=f"Album: {current_album_display_title}",
                    visible=True
                )
        elif self.album_task_id is not None and not is_album_track_for_progress : 
             self.album_progress_display.update(self.album_task_id, visible=False)
             self.album_task_id = None
             self._current_album_title_for_progress = ""
             self._album_tracks_completed = 0
             self._album_tracks_total = 0
        
        should_show_album_panel = not progress.is_video and progress.is_album_track
        
        self._recreate_live_if_layout_changed(should_show_album_panel)

        if self.live and self.live._started:
            self.live.refresh()


    def start_display(self, initial_message: str = "Initializing..."):
        """Starts the live display."""
        self.track_info_text.plain = initial_message
        self._recreate_live_if_layout_changed(show_album_panel=False)
        self.logger.debug("Rich Live display started/updated.")

    def stop_display(self):
        """Stops the live display if it's active."""
        if self.live and self.live._started: 
            self.live.stop()
            self.logger.debug("Rich Live display stopped.")
        self.reset_progress_state()

    def clear_current_track_info(self):
        """Clears the current track information panel."""
        self.track_info_text.plain = ""

    def set_overall_progress_description(self, description: str):
        """Sets the description for the overall progress bar."""
        if self.overall_task_id is not None:
            self.overall_progress_display.update(self.overall_task_id, description=description)
