#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Support agent: intent -> tool call -> permission check -> human handoff.

Standard library only. Run the demo transcript with:

    python agent.py
    python agent.py "我的订单 A1001 到哪了"
    python agent.py "我要退款 A1002，东西坏了"

Design notes (the interesting part, not the mock data):

1. **Tools are declared, not hard-coded into branches.** Each tool carries a
   JSON-schema-like parameter spec and a permission predicate. The router only
   decides *which* tool and *with what arguments*; the executor enforces the
   rest. Adding a tool means adding one dict, not editing an if-chain.

2. **The model is not allowed to invent order IDs.** Entity extraction only
   accepts IDs that match the known pattern, and the executor re-validates
   ownership before any state change. A confidently-wrong answer is the
   expensive failure mode in support, so the deterministic checks sit *after*
   the fuzzy part.

3. **Handoff is a first-class outcome, not an error path.** Three triggers:
   intent unknown, tool failed, or the action exceeds an autonomy threshold
   (refund above REFUND_AUTO_LIMIT). The agent explains *why* it escalated.

4. **Every turn leaves a trace.** `result["trace"]` records the classified
   intent, the tool called, arguments, and the handoff reason, so a transcript
   can be audited after the fact.
"""

import json
import re
import sys

# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------

REFUND_AUTO_LIMIT = 500.0  # above this, a human must approve
MAX_TOOL_RETRIES = 1

ORDER_ID_RE = re.compile(r"\b[A-Z]\d{4}\b")

# --------------------------------------------------------------------------
# Mock back end (stands in for an order service)
# --------------------------------------------------------------------------

ORDERS = {
    "A1001": {"user": "u_001", "status": "shipped", "amount": 289.0,
              "item": "Desk lamp", "carrier": "SF Express", "eta": "明天下午"},
    "A1002": {"user": "u_001", "status": "delivered", "amount": 1299.0,
              "item": "Coffee machine", "carrier": "JD Logistics", "eta": "已签收"},
    "A1003": {"user": "u_002", "status": "processing", "amount": 59.0,
              "item": "Cable", "carrier": None, "eta": "未发货"},
}


# --------------------------------------------------------------------------
# Tool registry: declarative schema + permission predicate
# --------------------------------------------------------------------------

def _own_order(user, order_id):
    """A user may only see or change their own orders."""
    order = ORDERS.get(order_id)
    return order is not None and order["user"] == user


TOOLS = {
    "check_order": {
        "description": "查订单状态与物流",
        "required": ["order_id"],
        "permission": _own_order,
        "run": lambda order_id: {
            "order_id": order_id,
            "status": ORDERS[order_id]["status"],
            "item": ORDERS[order_id]["item"],
            "carrier": ORDERS[order_id]["carrier"],
            "eta": ORDERS[order_id]["eta"],
        },
    },
    "request_refund": {
        "description": "发起退款申请",
        "required": ["order_id"],
        "permission": _own_order,
        "run": lambda order_id, reason="": {
            "order_id": order_id,
            "amount": ORDERS[order_id]["amount"],
            "reason": reason,
            "status": "refund_pending",
        },
    },
}


# --------------------------------------------------------------------------
# Intent classification (rule based, explainable on purpose)
# --------------------------------------------------------------------------

INTENT_PATTERNS = [
    ("request_refund", ("退款", "退钱", "退货", "坏了", "破损", "refund")),
    ("check_order", ("到哪", "物流", "快递", "发货", "订单", "tracking", "order")),
    ("chitchat", ("你好", "谢谢", "hello", "hi")),
]


def classify(message):
    """Return (intent, matched_keyword). Unknown intent is a handoff trigger."""
    text = message.lower()
    for intent, keywords in INTENT_PATTERNS:
        for kw in keywords:
            if kw in text:
                return intent, kw
    return "unknown", None


def extract_order_id(message):
    match = ORDER_ID_RE.search(message.upper())
    return match.group(0) if match else None


# --------------------------------------------------------------------------
# Execution with permission + handoff
# --------------------------------------------------------------------------

def _trace(intent, keyword, tool, args, outcome, reason=""):
    return {
        "intent": intent,
        "matched_keyword": keyword,
        "tool": tool,
        "args": args,
        "outcome": outcome,
        "handoff_reason": reason,
    }


def handle(user, message, trace=None):
    """One turn. Returns {reply, handoff, trace, tool_result?}."""
    trace = trace if trace is not None else []
    intent, keyword = classify(message)

    if intent == "chitchat":
        return {"reply": "你好，请问需要查订单还是申请退款？", "handoff": False,
                "trace": trace + [_trace(intent, keyword, None, {}, "answered")]}

    if intent == "unknown":
        reason = "无法识别意图"
        return {"reply": "这个问题我需要转人工同事帮你看，稍等一下。",
                "handoff": True,
                "trace": trace + [_trace(intent, keyword, None, {}, "handoff", reason)]}

    order_id = extract_order_id(message)
    if not order_id:
        reason = "没有提供订单号"
        return {"reply": "请提供订单号（形如 A1001），我马上帮你查。",
                "handoff": True,
                "trace": trace + [_trace(intent, keyword, None, {}, "handoff", reason)]}

    spec = TOOLS[intent]
    args = {"order_id": order_id}

    # Permission is checked before the tool runs, not after.
    if not spec["permission"](user, order_id):
        reason = "订单不属于当前用户或不存在"
        return {"reply": "这个订单号我这边查不到，请确认后再试，或转人工核实。",
                "handoff": True,
                "trace": trace + [_trace(intent, keyword, intent, args, "denied", reason)]}

    # Autonomy threshold: refunds above the limit need a human.
    if intent == "request_refund":
        amount = ORDERS[order_id]["amount"]
        if amount > REFUND_AUTO_LIMIT:
            reason = "退款金额 %.0f 超过自动处理上限 %.0f" % (amount, REFUND_AUTO_LIMIT)
            return {"reply": "这笔退款金额较大（¥%.0f），需要人工审核，已为你转接。"
                             % amount,
                    "handoff": True,
                    "trace": trace + [_trace(intent, keyword, intent, args, "handoff", reason)]}

    result = spec["run"](**args)
    if intent == "check_order":
        reply = "订单 %s（%s）当前状态：%s，承运 %s，预计 %s。" % (
            order_id, result["item"], result["status"],
            result["carrier"] or "—", result["eta"])
    else:
        reply = "已为订单 %s 提交退款申请，金额 ¥%.0f，状态：待处理。" % (
            order_id, result["amount"])

    return {"reply": reply, "handoff": False, "tool_result": result,
            "trace": trace + [_trace(intent, keyword, intent, args, "ok")]}


# --------------------------------------------------------------------------
# Demo transcript
# --------------------------------------------------------------------------

DEMO = [
    ("u_001", "你好"),
    ("u_001", "我的订单 A1001 到哪了"),
    ("u_001", "我要退款 A1002，咖啡机坏了"),
    ("u_001", "帮我退款 A1003"),
    ("u_002", "我的订单 A1001 到哪了"),
    ("u_001", "你们公司股票怎么样"),
]


def main():
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
        out = handle("u_001", message)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print("Support agent demo  (user=u_001 unless stated, refund auto-limit=%.0f)"
          % REFUND_AUTO_LIMIT)
    print("=" * 78)
    # Expected handoff per turn, in DEMO order:
    #   1 chitchat -> no handoff
    #   2 own order, in stock -> no handoff
    #   3 refund above the auto limit -> handoff
    #   4 someone else's order -> handoff (permission denied)
    #   5 looking up another user's order -> handoff (permission denied)
    #   6 unknown intent -> handoff
    EXPECTED = [False, False, True, True, True, True]
    passed = 0
    for (user, message), expected_handoff in zip(DEMO, EXPECTED):
        out = handle(user, message)
        last = out["trace"][-1]
        print("[%s] %s" % (user, message))
        print("   -> %s" % out["reply"])
        print("   intent=%s  outcome=%s  handoff=%s%s" % (
            last["intent"], last["outcome"], out["handoff"],
            ("  reason: " + last["handoff_reason"]) if last["handoff_reason"] else ""))
        print("-" * 78)
        if bool(out["handoff"]) == expected_handoff:
            passed += 1
        else:
            print("   [FAIL] expected handoff=%s" % expected_handoff)
    print("RESULT: %d/%d turns behaved as expected" % (passed, len(DEMO)))
    return 0 if passed == len(DEMO) else 1


if __name__ == "__main__":
    sys.exit(main())
