from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.core.indexes import AccountIndex
from app.core.models import Account, Item


def print_accounts_table(console: Console, accounts: list[Account]) -> None:
    """Render a rich table of accounts."""
    table = Table(show_header=True, header_style='bold', box=None)
    table.add_column('Vanity', style='cyan', no_wrap=True)
    table.add_column('Steam ID64')
    table.add_column('Exists')
    table.add_column('Ban')
    table.add_column('Inventory')
    table.add_column('Items', justify='right')
    table.add_column('Sync')
    table.add_column('Last Sync')

    for acc in accounts:
        last_sync = (
            acc.last_successful_sync_at.strftime('%Y-%m-%d %H:%M')
            if acc.last_successful_sync_at else '—'
        )
        table.add_row(
            acc.vanity_name,
            acc.steam_id64 or '—',
            acc.account_exists_status.value,
            acc.account_ban_status.value,
            acc.inventory_visibility_status.value,
            str(acc.items_count_total),
            acc.sync_status.value,
            last_sync,
        )

    console.print(table)


def print_account_card(console: Console, account: Account) -> None:
    """Render a detailed account card."""
    last_sync = (
        account.last_successful_sync_at.strftime('%Y-%m-%d %H:%M')
        if account.last_successful_sync_at else 'never'
    )
    last_attempt = (
        account.last_sync_attempt_at.strftime('%Y-%m-%d %H:%M')
        if account.last_sync_attempt_at else 'never'
    )

    lines = [
        f'[bold cyan]{account.vanity_name}[/bold cyan]'
        + (f'  |  [dim]{account.steam_id64}[/dim]' if account.steam_id64 else ''),
        f'exists: {account.account_exists_status.value}'
        f'  |  ban: {account.account_ban_status.value}'
        f'  |  inventory: {account.inventory_visibility_status.value}',
        f'items: {account.items_count_total} total'
        f'  |  {account.marketable_items_count} marketable'
        f'  |  {account.tradable_items_count} tradable',
        f'sync: {account.sync_status.value}'
        f'  |  last success: {last_sync}'
        f'  |  last attempt: {last_attempt}',
    ]

    if account.sync_error_category.value != 'none':
        lines.append(f'error: [red]{account.sync_error_category.value}[/red]')

    if account.items:
        lines.append('')
        lines.append('[bold]Items:[/bold]')
        for item in account.items:
            t_flag = '[green]T[/green]' if item.tradable else '[dim]t[/dim]'
            m_flag = '[green]M[/green]' if item.marketable else '[dim]m[/dim]'
            lines.append(f'  {item.display_name}  x{item.quantity}  {t_flag}{m_flag}')

    console.print(Panel('\n'.join(lines), title='Account', border_style='dim'))


def print_find_results(console: Console, results: list[tuple[Account, Item]]) -> None:
    """Render find-command results as a rich table."""
    table = Table(show_header=True, header_style='bold', box=None)
    table.add_column('Account', style='cyan', no_wrap=True)
    table.add_column('Item')
    table.add_column('Qty', justify='right')
    table.add_column('T')
    table.add_column('M')

    for account, item in results:
        table.add_row(
            account.vanity_name,
            item.display_name,
            str(item.quantity),
            '[green]T[/green]' if item.tradable else '[dim]-[/dim]',
            '[green]M[/green]' if item.marketable else '[dim]-[/dim]',
        )

    console.print(table)
    unique_accounts = len({a.vanity_name for a, _ in results})
    console.print(f'  [dim]Found {len(results)} item(s) in {unique_accounts} account(s).[/dim]')


def print_stats(console: Console, index: AccountIndex, schema_version: str) -> None:
    """Render database statistics as a rich table."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column('Key', style='dim')
    table.add_column('Value')

    table.add_row('total', str(index.total_count))
    table.add_row('schema', schema_version)
    table.add_row('', '')
    table.add_row('exists', str(index.exists_count))
    table.add_row('not_found', str(index.not_found_count))
    table.add_row('unknown (exists)', str(index.unknown_exists_count))
    table.add_row('', '')
    table.add_row('vac_banned', str(index.vac_banned_count))
    table.add_row('not_banned', str(index.not_banned_count))
    table.add_row('unknown (ban)', str(index.unknown_ban_count))
    table.add_row('', '')
    table.add_row('public', str(index.public_count))
    table.add_row('private', str(index.private_count))
    table.add_row('unknown (inv)', str(index.unknown_inventory_count))
    table.add_row('empty public', str(index.empty_public_count))
    table.add_row('', '')
    table.add_row('sync success', str(index.success_count))
    table.add_row('sync partial', str(index.partial_success_count))
    table.add_row('sync failed', str(index.failed_count))
    table.add_row('never synced', str(index.never_synced_count))

    console.print(Panel(table, title='Database', border_style='cyan'))
    console.print('[dim]Proxy stats — available after Stage 5.[/dim]')
