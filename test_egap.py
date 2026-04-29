import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aiops_platform.settings")
import django
django.setup()

from genai.egap_protocol import egap_dispatch
from genai.policy_engine import evaluate_execution_policy
from genai.execution_safety import frequency_limit_config, sign_intent_payload

print("=== EGAP Protocol Smoke Test ===")

cases = [
    ("tail -n 100 /var/log/app.log",                                        "app-inventory", "diagnostic"),
    ("psql -h db -U user -d aiops -c 'UPDATE demo_inventory SET qty=qty+1'", "db",           "remediation"),
    ("docker compose restart app-orders",                                    "app-orders",    "remediation"),
    ("grep ERROR /var/log/nginx.log",                                        "gateway",       "diagnostic"),
]

for cmd, host, etype in cases:
    e = egap_dispatch(command=cmd, target_host=host, execution_type=etype, actor="test-runner")
    print(f"\n  [{etype}] {cmd[:60]}")
    print(f"    egap_version : {e['egap_version']}")
    print(f"    method       : {e['method']}")
    print(f"    permission   : {e['permission']}")
    print(f"    action_type  : {e['action_type']}")
    print(f"    decision     : {e['decision']}")
    print(f"    approval     : {e['approval']['state']}")
    print(f"    alert.anomaly: {e['alert']['anomaly']}")
    print(f"    identity     : {e['identity']['actor']} / {e['identity']['agent_id']}")

e2 = evaluate_execution_policy(command="tail -n 50 /var/log/nginx.log", target_host="gateway", execution_type="diagnostic")
assert e2["decision"] == "allowed", f"FAIL: {e2['decision']}"
print("\n  evaluate_execution_policy alias : OK")
print(f"  frequency_limit_config         : {frequency_limit_config()}")
print("\n=== All OK ===")
