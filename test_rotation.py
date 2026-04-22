"""
Force the rotation path: poison a key with a synthetic cooldown,
then confirm _get_client skips it and picks another. Also prove
that a real 429 from the library gets mapped to a cooldown + retry.
"""
import asyncio
import os
import sys
import time

os.environ.setdefault("DISCORD_BOT_TOKEN", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot


def banner(s):
    print("\n" + "=" * 70)
    print(s)
    print("=" * 70)


def test_skips_cooling_keys():
    banner("A. Cool all but one key -> _get_client returns the survivor")
    survivor = bot.API_KEYS[2]
    for k in bot.API_KEYS:
        if k != survivor:
            bot._key_cooldowns[k] = time.time() + 60
    c, chosen = bot._get_client()
    assert chosen == survivor, f"Expected survivor ...{survivor[-6:]}, got ...{chosen[-6:]}"
    print(f"  PASS — picked ...{chosen[-6:]} (survivor)")
    bot._key_cooldowns.clear()


def test_all_cooling_waits_for_soonest():
    banner("B. All keys cooling -> _get_client sleeps to soonest then returns")
    now = time.time()
    for i, k in enumerate(bot.API_KEYS):
        bot._key_cooldowns[k] = now + (5 + i)  # soonest ready in 5s
    t0 = time.time()
    c, chosen = bot._get_client()
    elapsed = time.time() - t0
    assert 4.0 <= elapsed <= 7.0, f"Expected ~5s wait, got {elapsed:.1f}s"
    print(f"  PASS — slept {elapsed:.2f}s, woke with key ...{chosen[-6:]}")
    bot._key_cooldowns.clear()


def test_real_429_triggers_rotation():
    banner("C. Simulate real 429 from the API layer -> _generate_with_retry rotates")
    from google.genai import errors as genai_errors

    rotation_log = []
    attempt = {"n": 0}

    class FakeResponse:
        status_code = 429

    class FakeModels:
        def __init__(self, key):
            self.key = key

        def generate_content(self, *, model, contents, config):
            rotation_log.append(self.key)
            attempt["n"] += 1
            # First 2 calls 429, third succeeds
            if attempt["n"] < 3:
                raise genai_errors.ClientError(
                    429,
                    {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                               "message": "Resource exhausted."}},
                    FakeResponse(),
                )

            class R:
                text = "OK-synthetic-answer"

            return R()

    class FakeClient:
        def __init__(self, key):
            self.models = FakeModels(key)

    # Monkey-patch _get_client so it returns FakeClients but still rotates keys via bot's state
    real_get_client = bot._get_client
    original_clients = bot._clients.copy()
    bot._clients.clear()

    def fake_get_client():
        key = bot.API_KEYS[bot._key_idx % len(bot.API_KEYS)]
        if key not in bot._clients:
            bot._clients[key] = FakeClient(key)
        return bot._clients[key], key

    bot._get_client = fake_get_client
    try:
        resp = bot._generate_with_retry(model="x", contents="y", config=None)
        assert resp.text == "OK-synthetic-answer"
        print(f"  Keys hit in order: {[f'...{k[-6:]}' for k in rotation_log]}")
        unique = len({k for k in rotation_log})
        assert unique >= 2, f"Expected rotation across keys, only saw {unique} unique"
        # First two keys should now be in cooldown
        cooling = {k for k, t in bot._key_cooldowns.items() if t > time.time()}
        print(f"  Cooldowns after test: {[f'...{k[-6:]}' for k in cooling]}")
        assert len(cooling) >= 2, "Expected at least 2 keys in cooldown"
        print(f"  PASS — rotation fired {unique} times, {len(cooling)} keys cooling")
    finally:
        bot._get_client = real_get_client
        bot._clients = original_clients
        bot._key_cooldowns.clear()


def main():
    print(f"Keys available: {len(bot.API_KEYS)}")
    assert len(bot.API_KEYS) >= 3, "Need >=3 keys to meaningfully test rotation"
    test_skips_cooling_keys()
    test_all_cooling_waits_for_soonest()
    test_real_429_triggers_rotation()
    banner("ALL ROTATION TESTS PASSED")


if __name__ == "__main__":
    main()
