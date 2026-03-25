from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.core.indexes import AccountIndex
from app.core.models import Account, Item

if TYPE_CHECKING:
    from app.proxy.manager import ProxyManager


def print_accounts_table(console: Console, accounts: list[Account]) -> None:
    """Render a rich table of accounts."""
    has_pricing = any(a.total_inventory_value is not None for a in accounts)

    table = Table(show_header=True, header_style='bold', box=None)
    table.add_column('Vanity', style='cyan', no_wrap=True)
    table.add_column('Steam ID64')
    table.add_column('Exists')
    table.add_column('Ban')
    table.add_column('Inventory')
    table.add_column('Items', justify='right')
    if has_pricing:
        table.add_column('Value', justify='right')
    table.add_column('Sync')
    table.add_column('Last Sync')

    for acc in accounts:
        last_sync = (
            acc.last_successful_sync_at.strftime('%Y-%m-%d %H:%M')
            if acc.last_successful_sync_at else '—'
        )
        row = [
            acc.vanity_name,
            acc.steam_id64 or '—',
            acc.account_exists_status.value,
            acc.account_ban_status.value,
            acc.inventory_visibility_status.value,
            str(acc.items_count_total),
        ]
        if has_pricing:
            row.append(
                f'{acc.total_inventory_value:.2f}' if acc.total_inventory_value is not None else '—'
            )
        row += [acc.sync_status.value, last_sync]
        table.add_row(*row)

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

    items_line = (
        f'items: {account.items_count_total} total'
        f'  |  {account.marketable_items_count} marketable'
        f'  |  {account.tradable_items_count} tradable'
    )
    if account.total_inventory_value is not None:
        currency = next(
            (item.currency for item in account.items if item.currency), ''
        )
        items_line += f'  |  value: [yellow]{account.total_inventory_value:.2f} {currency}[/yellow]'

    lines = [
        f'[bold cyan]{account.vanity_name}[/bold cyan]'
        + (f'  |  [dim]{account.steam_id64}[/dim]' if account.steam_id64 else ''),
        f'exists: {account.account_exists_status.value}'
        f'  |  ban: {account.account_ban_status.value}'
        f'  |  inventory: {account.inventory_visibility_status.value}',
        items_line,
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
            price_str = ''
            if item.price is not None:
                price_str = f'  [yellow]{item.price:.2f} {item.currency or ""}[/yellow]'
            lines.append(f'  {item.display_name}  x{item.quantity}  {t_flag}{m_flag}{price_str}')

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


def print_stats(
    console: Console,
    index: AccountIndex,
    schema_version: str,
    proxy_manager: ProxyManager | None = None,
) -> None:
    """Render database and proxy statistics."""
    db_table = Table(show_header=False, box=None, padding=(0, 2))
    db_table.add_column('Key', style='dim')
    db_table.add_column('Value')

    db_table.add_row('total', str(index.total_count))
    db_table.add_row('schema', schema_version)
    db_table.add_row('', '')
    db_table.add_row('exists', str(index.exists_count))
    db_table.add_row('not_found', str(index.not_found_count))
    db_table.add_row('unknown (exists)', str(index.unknown_exists_count))
    db_table.add_row('', '')
    db_table.add_row('vac_banned', str(index.vac_banned_count))
    db_table.add_row('not_banned', str(index.not_banned_count))
    db_table.add_row('unknown (ban)', str(index.unknown_ban_count))
    db_table.add_row('', '')
    db_table.add_row('public', str(index.public_count))
    db_table.add_row('private', str(index.private_count))
    db_table.add_row('unknown (inv)', str(index.unknown_inventory_count))
    db_table.add_row('empty public', str(index.empty_public_count))
    db_table.add_row('', '')
    db_table.add_row('sync success', str(index.success_count))
    db_table.add_row('sync partial', str(index.partial_success_count))
    db_table.add_row('sync failed', str(index.failed_count))
    db_table.add_row('never synced', str(index.never_synced_count))

    console.print(Panel(db_table, title='Database', border_style='cyan'))

    if proxy_manager is None or proxy_manager.is_direct_mode:
        console.print('[dim]Proxies: direct connection (no pool configured)[/dim]')
        return

    summary = proxy_manager.proxy_summary()
    px_table = Table(show_header=True, header_style='bold', box=None)
    px_table.add_column('Proxy', style='cyan', no_wrap=True)
    px_table.add_column('Alive')
    px_table.add_column('Circuit')
    px_table.add_column('OK', justify='right')
    px_table.add_column('Fail', justify='right')
    px_table.add_column('Avg ms', justify='right')
    px_table.add_column('Active', justify='right')

    for row in summary:
        alive_str = '[green]yes[/green]' if row['alive'] else '[red]no[/red]'
        circuit_str = row['circuit']
        if circuit_str == 'open':
            circuit_str = f'[red]{circuit_str}[/red]'
        elif circuit_str == 'half_open':
            circuit_str = f'[yellow]{circuit_str}[/yellow]'
        px_table.add_row(
            row['url'],
            alive_str,
            circuit_str,
            str(row['ok']),
            str(row['fail']),
            str(row['avg_ms']),
            str(row['active']),
        )

    console.print(Panel(px_table, title=f'Proxies ({len(summary)})', border_style='cyan'))
