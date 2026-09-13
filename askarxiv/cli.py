"""Command line entry points."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from askarxiv import config
from askarxiv.harvest import Harvester, HarvestState, months_ago

app = typer.Typer(add_completion=False, help="Ask arXiv: harvest, index, search, evaluate.")
console = Console()


@app.command()
def harvest(
    months: int = typer.Option(6, help="How far back to harvest."),
    category: str = typer.Option("cs.AI", help="Keep records carrying this category."),
    oai_set: str = typer.Option("cs", help="OAI set. arXiv sets stop at the archive level."),
    out: Path = typer.Option(Path("data/papers.jsonl"), help="JSONL sink."),
    state: Path = typer.Option(Path(".state/harvest.json"), help="Checkpoint file."),
    restart: bool = typer.Option(False, help="Ignore an existing checkpoint and start over."),
    until: str | None = typer.Option(None, help="ISO end date. Defaults to today."),
) -> None:
    """Harvest arXiv metadata over OAI-PMH, resumably."""
    from_date = months_ago(months)
    until_date = date.fromisoformat(until) if until else None

    existing = HarvestState.load(state)
    if existing and not restart:
        if existing.finished:
            console.print(
                f"[green]Harvest already complete[/]: {existing.records_kept} records in {out}. "
                "Pass --restart to redo it."
            )
            raise typer.Exit(0)
        console.print(f"[yellow]Resuming[/] from page {existing.pages_fetched}.")

    harvester = Harvester()
    kept = 0
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("harvesting…")
        for _paper in harvester.harvest(
            out_path=out,
            state_path=state,
            from_date=from_date,
            until_date=until_date,
            oai_set=oai_set,
            category=category,
            resume=not restart,
        ):
            kept += 1
            if kept % 50 == 0:
                progress.update(task, description=f"harvesting… {kept} {category} papers")

    final = HarvestState.load(state)
    seen = final.records_seen if final else kept
    console.print(
        f"[green]Done[/]: kept {kept} {category} papers out of {seen} {oai_set} records "
        f"since {from_date.isoformat()} → {out}"
    )


@app.command()
def config_show() -> None:
    """Print effective configuration, so a surprising run can be explained."""
    console.print(f"endpoint : {config.OAI_ENDPOINT}")
    console.print(f"user-agent: {config.USER_AGENT}")
    console.print(f"database : {config.DbConfig().dsn.replace(config.DbConfig().password, '***')}")


if __name__ == "__main__":
    app()
