"""
Generates a self-contained HTML reconciliation report from final AgentState.
"""
from __future__ import annotations

import webbrowser
from datetime import datetime
from pathlib import Path

from agent.models import AgentState, Discrepancy


def _badge(text: str, color: str) -> str:
    return f'<span class="badge" style="background:{color}">{text}</span>'


def _confidence_badge(c: str) -> str:
    colors = {"high": "#c0392b", "medium": "#e67e22", "low": "#7f8c8d"}
    return _badge(c.upper(), colors.get(c, "#95a5a6"))


def _decision_badge(d: str) -> str:
    colors = {
        "approve":  "#27ae60",
        "reject":   "#c0392b",
        "escalate": "#e67e22",
        "no_decision": "#95a5a6",
    }
    labels = {
        "approve":  "APPROVED",
        "reject":   "REJECTED",
        "escalate": "ESCALATED",
        "no_decision": "PENDING",
    }
    return _badge(labels.get(d, d.upper()), colors.get(d, "#95a5a6"))


def _status_color(status: str) -> str:
    if status == "clean":
        return "#27ae60"
    if status == "complete_all_resolved":
        return "#2980b9"
    if status == "complete_with_escalations":
        return "#e67e22"
    return "#95a5a6"


def generate_report(state: AgentState, output_path: str = "report.html", auto_open: bool = True) -> str:
    """
    Writes an HTML report to output_path and optionally opens it in the browser.
    Returns the absolute path to the file.
    """
    discrepancies: list[Discrepancy] = state.get("discrepancies", [])
    decisions: dict = state.get("human_decisions", {})
    status = state.get("status", "unknown")
    bank_count = len(state.get("bank_transactions", []))
    stripe_count = len(state.get("stripe_transactions", []))

    approved  = sum(1 for v in decisions.values() if v == "approve")
    rejected  = sum(1 for v in decisions.values() if v == "reject")
    escalated = sum(1 for v in decisions.values() if v == "escalate")
    pending   = len(discrepancies) - approved - rejected - escalated

    generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    status_color = _status_color(status)

    # ── Discrepancy rows ───────────────────────────────────────────────────────
    if discrepancies:
        rows = ""
        for i, d in enumerate(discrepancies):
            decision = decisions.get(i, decisions.get(str(i), "no_decision"))
            rows += f"""
            <tr>
                <td class="idx">#{i}</td>
                <td><code>{d.bank_txn_id}</code></td>
                <td><code>{d.stripe_txn_id}</code></td>
                <td>{_confidence_badge(d.confidence)}</td>
                <td class="reason">{d.reason}</td>
                <td class="action">{d.suggested_action.replace('_', ' ')}</td>
                <td>{_decision_badge(decision)}</td>
            </tr>"""
        table_html = f"""
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Bank ID</th>
                    <th>Stripe ID</th>
                    <th>Confidence</th>
                    <th>Reason</th>
                    <th>Suggested Action</th>
                    <th>Decision</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>"""
    else:
        table_html = '<div class="clean-banner">All transactions reconciled cleanly. No discrepancies found.</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reconciliation Report</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f0f2f5;
      color: #1a1a2e;
      padding: 32px 20px 60px;
    }}

    /* ── Header ── */
    .header {{
      max-width: 960px;
      margin: 0 auto 28px;
    }}
    .header h1 {{
      font-size: 1.8rem;
      font-weight: 700;
      color: #1a1a2e;
      margin-bottom: 4px;
    }}
    .header .meta {{
      font-size: 0.85rem;
      color: #6b7280;
    }}

    /* ── Status banner ── */
    .status-banner {{
      max-width: 960px;
      margin: 0 auto 24px;
      background: {status_color};
      color: #fff;
      border-radius: 10px;
      padding: 16px 24px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 600;
      font-size: 1rem;
      letter-spacing: 0.01em;
    }}
    .status-dot {{
      width: 12px; height: 12px;
      border-radius: 50%;
      background: rgba(255,255,255,0.6);
      flex-shrink: 0;
    }}

    /* ── Stat cards ── */
    .cards {{
      max-width: 960px;
      margin: 0 auto 28px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 14px;
    }}
    .card {{
      background: #fff;
      border-radius: 10px;
      padding: 20px 16px 16px;
      text-align: center;
      box-shadow: 0 1px 4px rgba(0,0,0,0.07);
    }}
    .card .num {{
      font-size: 2rem;
      font-weight: 700;
      line-height: 1;
      margin-bottom: 6px;
    }}
    .card .label {{
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: #6b7280;
    }}
    .card.blue   .num {{ color: #2563eb; }}
    .card.red    .num {{ color: #dc2626; }}
    .card.orange .num {{ color: #d97706; }}
    .card.green  .num {{ color: #16a34a; }}
    .card.gray   .num {{ color: #6b7280; }}

    /* ── Section ── */
    .section {{
      max-width: 960px;
      margin: 0 auto 32px;
    }}
    .section h2 {{
      font-size: 1rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #6b7280;
      margin-bottom: 14px;
      border-bottom: 1px solid #e5e7eb;
      padding-bottom: 8px;
    }}

    /* ── Table ── */
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #fff;
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 1px 4px rgba(0,0,0,0.07);
      font-size: 0.88rem;
    }}
    thead tr {{
      background: #1a1a2e;
      color: #fff;
    }}
    th {{
      text-align: left;
      padding: 12px 14px;
      font-weight: 600;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    td {{
      padding: 13px 14px;
      border-bottom: 1px solid #f3f4f6;
      vertical-align: top;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #f9fafb; }}
    td.idx {{ color: #9ca3af; font-size: 0.8rem; width: 36px; }}
    td.reason {{ max-width: 260px; line-height: 1.45; }}
    td.action {{ max-width: 180px; font-size: 0.82rem; color: #6b7280; line-height: 1.4; }}
    code {{
      background: #f3f4f6;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.82rem;
      font-family: "SF Mono", "Fira Code", monospace;
    }}

    /* ── Badge ── */
    .badge {{
      display: inline-block;
      padding: 3px 9px;
      border-radius: 20px;
      font-size: 0.72rem;
      font-weight: 700;
      color: #fff;
      letter-spacing: 0.05em;
      white-space: nowrap;
    }}

    /* ── Clean banner ── */
    .clean-banner {{
      background: #f0fdf4;
      border: 1px solid #86efac;
      color: #166534;
      border-radius: 10px;
      padding: 24px;
      text-align: center;
      font-weight: 500;
    }}

    /* ── Legend ── */
    .legend {{
      background: #fff;
      border-radius: 10px;
      padding: 18px 20px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.07);
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.84rem;
      color: #374151;
    }}

    /* ── Data source bar ── */
    .source-bar {{
      background: #fff;
      border-radius: 10px;
      padding: 16px 20px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.07);
      display: flex;
      gap: 32px;
      font-size: 0.88rem;
    }}
    .source-item strong {{ color: #1a1a2e; }}
    .source-item span {{ color: #6b7280; }}

    /* ── Footer ── */
    .footer {{
      max-width: 960px;
      margin: 40px auto 0;
      text-align: center;
      font-size: 0.8rem;
      color: #9ca3af;
    }}
  </style>
</head>
<body>

  <div class="header">
    <h1>Transaction Reconciliation Report</h1>
    <div class="meta">Generated {generated_at}</div>
  </div>

  <div class="status-banner">
    <div class="status-dot"></div>
    {status.replace("_", " ").upper()}
  </div>

  <div class="cards">
    <div class="card blue">
      <div class="num">{bank_count}</div>
      <div class="label">Bank Transactions</div>
    </div>
    <div class="card blue">
      <div class="num">{stripe_count}</div>
      <div class="label">Stripe Transactions</div>
    </div>
    <div class="card red">
      <div class="num">{len(discrepancies)}</div>
      <div class="label">Discrepancies</div>
    </div>
    <div class="card green">
      <div class="num">{approved}</div>
      <div class="label">Approved</div>
    </div>
    <div class="card red">
      <div class="num">{rejected}</div>
      <div class="label">Rejected</div>
    </div>
    <div class="card orange">
      <div class="num">{escalated}</div>
      <div class="label">Escalated</div>
    </div>
    <div class="card gray">
      <div class="num">{pending}</div>
      <div class="label">Pending</div>
    </div>
  </div>

  <div class="section">
    <h2>Discrepancies Found</h2>
    {table_html}
  </div>

  <div class="section">
    <h2>Decision Legend</h2>
    <div class="legend">
      <div class="legend-item">{_decision_badge("approve")} &nbsp;Acknowledged — no financial action needed</div>
      <div class="legend-item">{_decision_badge("reject")} &nbsp;Confirmed error — finance team to correct</div>
      <div class="legend-item">{_decision_badge("escalate")} &nbsp;Needs senior review before action</div>
      <div class="legend-item">{_confidence_badge("high")} &nbsp;Unambiguous mismatch</div>
      <div class="legend-item">{_confidence_badge("medium")} &nbsp;Likely mismatch, verify first</div>
      <div class="legend-item">{_confidence_badge("low")} &nbsp;Uncertain — always escalated</div>
    </div>
  </div>

  <div class="footer">
    Autonomous Reconciliation Agent &nbsp;·&nbsp; LangGraph + Claude &nbsp;·&nbsp; Learning Project
  </div>

</body>
</html>"""

    path = Path(output_path).resolve()
    path.write_text(html, encoding="utf-8")

    if auto_open:
        webbrowser.open(path.as_uri())

    return str(path)
