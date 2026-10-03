"""
simulate.py — generates the entire synthetic marketing world.

Run:  python -m generator.simulate --config config/simulation.yml --out raw

Outputs (all relative to --out):
  segment_events/events_YYYY-MM.jsonl   Segment-spec track/page/identify events
  salesforce/accounts.csv
  salesforce/leads.csv
  salesforce/contacts.csv
  salesforce/campaigns.csv
  salesforce/campaign_members.csv
  salesforce/opportunities.csv
  salesforce/opportunity_stage_history.csv
  ad_platforms/spend.csv
  ../ground_truth/channel_contribution.csv
  ../ground_truth/account_touch_credit.csv
  ../ground_truth/run_manifest.json

The ground_truth/ files are the reason this project exists: they hold the real
per-channel contribution that generated each conversion. No production dataset
has this. Your attribution scorecard is scored against these files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

import numpy as np
import yaml

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

FIRST_NAMES = ["Priya","Marcus","Elena","Tom","Aisha","Kenji","Sofia","Liam","Nadia","Owen",
               "Grace","Diego","Hana","Callum","Ines","Raj","Mei","Felix","Zara","Oscar",
               "Lucia","Amir","Nora","Ethan","Yuki","Sana","Ben","Clara","Ivan","Tara"]
LAST_NAMES  = ["Nair","Holt","Vasquez","Okafor","Lindqvist","Tanaka","Moreau","Byrne","Haddad",
               "Whitfield","Dalgaard","Ferreira","Kaur","Novak","Ibrahim","Sorensen","Zhang",
               "Mbeki","Rossi","Kowalski","Andersen","Silva","Petrov","Ng","Dubois"]
COMPANY_HEADS = ["Northwind","Arclight","Cobalt","Meridian","Silverline","Vantage","Kestrel",
                 "Harbourpoint","Ridgeway","Lumen","Beacon","Orbital","Crestwave","Tallgrass",
                 "Ironbark","Solstice","Bluepeak","Wren","Copperfield","Havenroad","Quarry",
                 "Stonebridge","Fairweather","Latchkey","Windward","Tidewater","Foxglove"]
COMPANY_TAILS = ["Systems","Group","Holdings","Labs","Networks","Digital","Partners","Industries",
                 "Technologies","Capital","Logistics","Health","Media","Analytics"]

ROLES = [("Champion", 0.38), ("Technical Evaluator", 0.27),
         ("Economic Buyer", 0.16), ("End User", 0.13), ("Procurement", 0.06)]

PAGES = ["/", "/products/megaport-virtual-edge", "/pricing", "/solutions/multicloud",
         "/docs/getting-started", "/blog/naas-vs-mpls", "/locations", "/partners",
         "/contact", "/resources/webinar-replay", "/company/about"]

DEVICES = [("desktop", 0.63), ("mobile", 0.30), ("tablet", 0.07)]
BROWSERS = [("Chrome", 0.61), ("Safari", 0.20), ("Edge", 0.11), ("Firefox", 0.08)]

STAGES = ["Discovery", "Technical Validation", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]


def weighted_choice(rng, pairs):
    names = [p[0] for p in pairs]
    probs = np.array([p[1] for p in pairs], dtype=float)
    probs = probs / probs.sum()
    return str(rng.choice(names, p=probs))


def stable_id(prefix: str, *parts) -> str:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]
    return f"{prefix}_{h}"


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


# --------------------------------------------------------------------------- #
# generator
# --------------------------------------------------------------------------- #

class World:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg["seed"])
        random.seed(cfg["seed"])
        self.start = datetime.fromisoformat(cfg["start_date"])
        self.end = datetime.fromisoformat(cfg["end_date"])
        self.span_days = (self.end - self.start).days

        self.channels = cfg["channels"]
        self.ch_names = list(self.channels.keys())
        self.entry_p = self._norm([self.channels[c]["entry_weight"] for c in self.ch_names])
        self.repeat_p = self._norm([self.channels[c]["repeat_weight"] for c in self.ch_names])

        self.outage = cfg["noise"]["tracking_outage"]
        self.outage_start = datetime.fromisoformat(self.outage["start"])
        self.outage_end = datetime.fromisoformat(self.outage["end"]) + timedelta(days=1)

        self.campaigns = self._build_campaigns()

        # collectors
        self.accounts, self.persons, self.leads, self.contacts = [], [], [], []
        self.events, self.opps, self.stage_hist = [], [], []
        self.campaign_members, self.spend_rows = [], []
        self.truth_rows = []

    @staticmethod
    def _norm(x):
        a = np.array(x, dtype=float)
        return a / a.sum()

    # ---------------- campaigns ---------------- #
    def _build_campaigns(self):
        """One campaign per (channel, fiscal quarter). Handles the rename case."""
        rn = self.cfg["noise"]["campaign_rename"]
        camps = {}
        cur = self.start
        while cur < self.end:
            fy = cur.year + (1 if cur.month >= 7 else 0)
            q = ((cur.month - 7) % 12) // 3 + 1
            for ch in self.ch_names:
                cid = stable_id("cmp", ch, fy, q)
                if cid in camps:
                    continue
                name = f"FY{str(fy)[2:]}-Q{q}-{ch.replace('_','-').title()}"
                camps[cid] = {
                    "campaign_id": cid,
                    "campaign_name": name,
                    "channel": ch,
                    "fiscal_year": f"FY{str(fy)[2:]}",
                    "fiscal_quarter": f"Q{q}",
                    "start_date": cur.date().isoformat(),
                    "end_date": (cur + timedelta(days=90)).date().isoformat(),
                    "is_renamed": False,
                    "renamed_to": None,
                    "rename_effective": None,
                }
            cur += timedelta(days=91)

        # inject the rename on one real campaign
        target = next(iter([c for c in camps.values() if c["channel"] == "content_syndication"]))
        target["campaign_name"] = rn["old_name"]
        target["is_renamed"] = True
        target["renamed_to"] = rn["new_name"]
        target["rename_effective"] = rn["effective"]
        return camps

    def campaign_for(self, channel, when: datetime):
        fy = when.year + (1 if when.month >= 7 else 0)
        q = ((when.month - 7) % 12) // 3 + 1
        cid = stable_id("cmp", channel, fy, q)
        c = self.campaigns.get(cid)
        if c is None:  # edge of range
            c = next(iter([v for v in self.campaigns.values() if v["channel"] == channel]))
        name = c["campaign_name"]
        if c["is_renamed"] and when.date().isoformat() >= c["rename_effective"]:
            name = c["renamed_to"]
        return c["campaign_id"], name

    # ---------------- entities ---------------- #
    def make_account(self, i):
        rng = self.rng
        regions = self.cfg["regions"]
        region = weighted_choice(rng, [(k, v["weight"]) for k, v in regions.items()])
        ind = weighted_choice(rng, [(d["name"], d["weight"]) for d in self.cfg["industries"]])
        band = weighted_choice(rng, [(d["name"], d["weight"]) for d in self.cfg["employee_bands"]])
        ind_mult = next(d["icp_mult"] for d in self.cfg["industries"] if d["name"] == ind)
        band_row = next(d for d in self.cfg["employee_bands"] if d["name"] == band)

        name = f"{random.choice(COMPANY_HEADS)} {random.choice(COMPANY_TAILS)}"
        acct_id = stable_id("acc", i, name)
        icp_raw = ind_mult * band_row["icp_mult"] * float(rng.normal(1.0, 0.18))
        return {
            "account_id": acct_id,
            "account_name": name,
            "industry": ind,
            "employee_band": band,
            "region": region,
            "country": {"NA": "United States", "EMEA": "United Kingdom", "APAC": "Australia"}[region],
            "icp_score_raw": round(max(icp_raw, 0.05), 4),
            "deal_size_mult": band_row["deal_size_mult"],
            "win_rate_mult": regions[region]["win_rate_mult"],
            "created_date": None,   # filled from first touch
        }

    def make_persons(self, acct):
        rng = self.rng
        pv = self.cfg["volumes"]["persons_per_account"]
        n = int(np.clip(rng.triangular(pv["min"], pv["mode"], pv["max"] + 0.999), pv["min"], pv["max"]))
        out = []
        dom = acct["account_name"].lower().replace(" ", "").replace("&", "") + ".com"
        for j in range(n):
            fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            pid = stable_id("per", acct["account_id"], j, fn, ln)
            out.append({
                "person_id": pid,
                "account_id": acct["account_id"],
                "first_name": fn,
                "last_name": ln,
                "email": f"{fn.lower()}.{ln.lower()}@{dom}",
                "role": weighted_choice(rng, ROLES),
                "anonymous_ids": [],
            })
        return out

    # ---------------- journeys ---------------- #
    def build_journey(self, acct, persons):
        """Return (touchpoints, decision_dt). Touchpoints carry latent weights."""
        rng = self.rng
        jc = self.cfg["journey"]
        n_touch = int(np.clip(rng.geometric(1.0 / jc["touches_mean"]),
                              jc["touches_min"], jc["touches_max"]))

        first_offset = int(rng.uniform(0, self.span_days - 120))
        t = self.start + timedelta(days=first_offset,
                                   hours=int(rng.integers(6, 22)),
                                   minutes=int(rng.integers(0, 60)))

        touches, seen_counts = [], defaultdict(int)
        for k in range(n_touch):
            ch = (str(rng.choice(self.ch_names, p=self.entry_p)) if k == 0
                  else str(rng.choice(self.ch_names, p=self.repeat_p)))
            person = random.choice(persons)
            touches.append({"ts": t, "channel": ch, "person": person, "position": k})
            gap = max(1, int(rng.exponential(self.channels[ch]["latency_days"])))
            t = t + timedelta(days=gap, hours=int(rng.integers(0, 12)))
            if t > self.end:
                touches = touches[:k + 1]
                break

        decision_dt = touches[-1]["ts"] + timedelta(days=int(rng.exponential(9)) + 1)

        # latent contribution per touch
        total_w = 0.0
        for tp in touches:
            days_before = max((decision_dt - tp["ts"]).days, 0)
            base = self.channels[tp["channel"]]["true_effect"]
            decay = math.exp(-jc["decay_lambda"] * days_before)
            sat = jc["saturation_k"] ** seen_counts[tp["channel"]]
            seen_counts[tp["channel"]] += 1
            w = base * decay * sat
            tp["latent_weight"] = w
            total_w += w

        icp_z = (acct["icp_score_raw"] - 1.0) / 0.45
        logit = jc["base_logit"] + total_w + jc["icp_coefficient"] * icp_z
        p_convert = 1.0 / (1.0 + math.exp(-logit))
        converted = bool(self.rng.random() < p_convert)
        return touches, decision_dt, total_w, p_convert, converted

    # ---------------- emission ---------------- #
    def emit_events(self, acct, touches):
        rng = self.rng
        noise = self.cfg["noise"]
        for tp in touches:
            ts, ch, person = tp["ts"], tp["channel"], tp["person"]

            # tracking outage: silently drop
            if ch == self.outage["channel"] and self.outage_start <= ts < self.outage_end:
                tp["dropped"] = True
                continue
            tp["dropped"] = False

            anon = person["anonymous_ids"]
            if not anon or rng.random() < 0.25:
                new_anon = str(uuid.UUID(bytes=bytes(rng.integers(0, 256, 16, dtype=np.uint8))))
                anon.append(new_anon)
            anonymous_id = anon[-1]

            cid, cname = self.campaign_for(ch, ts)
            src, med = self._utm_for(ch)
            if rng.random() < noise["utm_dirty_rate"]:
                src = self._dirty(src)

            session_id = stable_id("ses", anonymous_id, ts.date(), int(ts.hour // 3))
            n_pages = int(np.clip(rng.geometric(0.42), 1, 9))
            is_bot = rng.random() < noise["bot_session_rate"]
            if is_bot:
                n_pages = int(rng.integers(40, 180))

            for pv in range(n_pages):
                pts = ts + timedelta(seconds=int(rng.integers(5, 240)) * (pv + 1))
                self.events.append({
                    "type": "page",
                    "messageId": stable_id("msg", anonymous_id, pts, pv),
                    "anonymousId": anonymous_id,
                    "userId": None,
                    "timestamp": iso(pts),
                    "context": {
                        "page": {"path": random.choice(PAGES),
                                 "referrer": "https://www.google.com/" if "search" in ch else ""},
                        "campaign": {"source": src, "medium": med, "name": cname,
                                     "content": f"ad{int(rng.integers(1, 9))}", "term": None},
                        "userAgent": ("Mozilla/5.0 (compatible; crawler/1.0)" if is_bot
                                      else f"Mozilla/5.0 ({weighted_choice(rng, DEVICES)})"),
                        "device": {"type": weighted_choice(rng, DEVICES)},
                        "locale": "en-AU" if acct["region"] == "APAC" else "en-US",
                        "ip": f"10.{int(rng.integers(0,255))}.{int(rng.integers(0,255))}.{int(rng.integers(1,254))}",
                    },
                    "properties": {"session_id": session_id, "page_index": pv,
                                   "browser": weighted_choice(rng, BROWSERS)},
                })

            # conversion event on the touch itself
            if rng.random() < self.cfg["funnel"]["visitor_to_known_rate"] or ch in (
                    "webinar", "content_syndication", "field_event", "email_nurture"):
                self.events.append({
                    "type": "identify",
                    "messageId": stable_id("msg", "id", anonymous_id, ts),
                    "anonymousId": anonymous_id,
                    "userId": person["person_id"],
                    "timestamp": iso(ts + timedelta(minutes=int(rng.integers(1, 30)))),
                    "traits": {
                        "email": (None if rng.random() < noise["null_email_rate"] else person["email"]),
                        "firstName": person["first_name"], "lastName": person["last_name"],
                        "company": acct["account_name"], "title": person["role"],
                        "country": acct["country"],
                    },
                    "context": {"campaign": {"source": src, "medium": med, "name": cname}},
                    "properties": {},
                })
                tp["identified"] = True
            else:
                tp["identified"] = False

            self.events.append({
                "type": "track",
                "event": {"webinar": "Webinar Registered",
                          "content_syndication": "Content Downloaded",
                          "field_event": "Event Attended",
                          "email_nurture": "Email Clicked"}.get(ch, "Form Submitted")
                         if tp.get("identified") else "Page Engaged",
                "messageId": stable_id("msg", "tr", anonymous_id, ts),
                "anonymousId": anonymous_id,
                "userId": person["person_id"] if tp.get("identified") else None,
                "timestamp": iso(ts + timedelta(minutes=int(rng.integers(1, 45)))),
                "properties": {"session_id": session_id, "campaign_id": cid,
                               "campaign_name": cname, "channel_hint": ch,
                               "form_id": f"frm_{int(rng.integers(100, 999))}" if tp.get("identified") else None},
                "context": {"campaign": {"source": src, "medium": med, "name": cname}},
            })

            self.campaign_members.append({
                "campaign_member_id": stable_id("cm", cid, person["person_id"], ts),
                "campaign_id": cid, "person_id": person["person_id"],
                "status": "Responded" if tp.get("identified") else "Sent",
                "created_date": ts.date().isoformat(),
            })

            cpt = self.channels[ch]["cost_per_touch"]
            if cpt > 0:
                booked = ts.date() + timedelta(days=self.cfg["noise"]["spend_late_arrival_days"])
                self.spend_rows.append({
                    "spend_date": ts.date().isoformat(),
                    "booked_date": booked.isoformat(),
                    "channel": ch, "campaign_id": cid, "campaign_name": cname,
                    "region": acct["region"],
                    "cost_usd": round(cpt * float(self.rng.normal(1.0, 0.22)), 2),
                    "impressions": int(max(1, self.rng.normal(340, 120))),
                    "clicks": 1,
                })

    def _utm_for(self, ch):
        return {
            "paid_search":         ("google", "cpc"),
            "paid_social":         ("linkedin", "paid-social"),
            "organic_search":      ("google", "organic"),
            "direct":              ("(direct)", "(none)"),
            "email_nurture":       ("marketo", "email"),
            "webinar":             ("on24", "webinar"),
            "content_syndication": ("techtarget", "syndication"),
            "partner_referral":    ("partner", "referral"),
            "field_event":         ("field", "event"),
        }[ch]

    def _dirty(self, s):
        r = self.rng.random()
        if r < 0.25:   return s.upper()
        if r < 0.45:   return s.title()
        if r < 0.65:   return f" {s} "
        if r < 0.80:   return s.replace("oo", "o").replace("in", "ln")
        if r < 0.92:   return s + "_"
        return s.replace("e", "3", 1)

    # ---------------- CRM ---------------- #
    def emit_crm(self, acct, persons, touches, converted, total_w, decision_dt):
        rng = self.rng
        fn = self.cfg["funnel"]
        noise = self.cfg["noise"]
        first_ts = touches[0]["ts"]
        acct["created_date"] = first_ts.date().isoformat()

        identified = [tp for tp in touches if tp.get("identified")]
        for tp in identified:
            p = tp["person"]
            lead_dt = tp["ts"]
            base = {
                "lead_id": stable_id("lead", p["person_id"], lead_dt),
                "person_id": p["person_id"],
                "account_id": acct["account_id"],
                "email": (None if rng.random() < noise["null_email_rate"] else p["email"]),
                "first_name": p["first_name"], "last_name": p["last_name"],
                "company": acct["account_name"], "title": p["role"],
                "country": acct["country"], "region": acct["region"],
                "lead_source": tp["channel"],
                "self_reported_source": (None if rng.random() < noise["self_reported_missing_rate"]
                                         else random.choice(["Colleague","Search","Event","Ad","Blog"])),
                "created_date": self._fmt_date(lead_dt, rng),
                "mql_date": None, "status": "Open",
            }
            if rng.random() < fn["known_to_mql_rate"]:
                mql_dt = lead_dt + timedelta(days=int(rng.exponential(5)))
                base["mql_date"] = self._fmt_date(mql_dt, rng)
                base["status"] = "MQL"
                if rng.random() < fn["mql_to_sql_rate"]:
                    base["status"] = "SQL"
            self.leads.append(base)
            if rng.random() < noise["duplicate_lead_rate"]:
                dup = dict(base)
                dup["lead_id"] = stable_id("lead", p["person_id"], lead_dt, "dup")
                dup["email"] = (base["email"] or "").replace("@", "+1@") or None
                dup["created_date"] = self._fmt_date(lead_dt + timedelta(days=int(rng.integers(1, 40))), rng)
                self.leads.append(dup)

        if not converted or not identified:
            return

        opp_dt = decision_dt
        cyc = self.cfg["funnel"]["sales_cycle_days"]
        cycle = int(max(cyc["min"], rng.normal(cyc["mean"], cyc["sd"])))
        close_dt = opp_dt + timedelta(days=cycle)
        if close_dt > self.end + timedelta(days=200):
            return

        arr = float(rng.lognormal(math.log(self.cfg["deal_size"]["base_arr"]),
                                  self.cfg["deal_size"]["lognormal_sigma"])) * acct["deal_size_mult"]
        p_win = min(0.95, fn["opp_to_won_rate"] * acct["win_rate_mult"] * (1 + 0.35 * min(total_w, 2.0)))
        won = bool(rng.random() < p_win)
        is_open = close_dt > self.end

        opp_id = stable_id("opp", acct["account_id"], opp_dt)
        primary = random.choice(identified)["person"]
        for p in persons:
            self.contacts.append({
                "contact_id": stable_id("con", p["person_id"]),
                "person_id": p["person_id"], "account_id": acct["account_id"],
                "email": p["email"], "first_name": p["first_name"], "last_name": p["last_name"],
                "title": p["role"], "created_date": self._fmt_date(first_ts, rng),
            })

        stage = ("Closed Won" if won else "Closed Lost") if not is_open else \
            random.choice(["Discovery", "Technical Validation", "Proposal", "Negotiation"])
        self.opps.append({
            "opportunity_id": opp_id, "account_id": acct["account_id"],
            "primary_contact_id": stable_id("con", primary["person_id"]),
            "opportunity_name": f"{acct['account_name']} - NaaS Expansion",
            "created_date": self._fmt_date(opp_dt, rng),
            "close_date": self._fmt_date(close_dt, rng),
            "stage": stage,
            "is_closed": (not is_open),
            "is_won": (won and not is_open),
            "amount_arr_usd": round(arr, 2),
            "region": acct["region"], "industry": acct["industry"],
            "sales_cycle_days": cycle,
        })

        cur = opp_dt
        path = STAGES[:STAGES.index(stage) + 1] if stage in STAGES else STAGES[:2]
        for s in path:
            self.stage_hist.append({
                "stage_history_id": stable_id("sh", opp_id, s),
                "opportunity_id": opp_id, "stage": s,
                "entered_at": cur.date().isoformat(),
            })
            cur += timedelta(days=max(1, cycle // max(len(path), 1)))

        # ---- GROUND TRUTH ----
        contributing = [tp for tp in touches if tp["latent_weight"] > 0]
        tw = sum(tp["latent_weight"] for tp in contributing) or 1.0
        for tp in contributing:
            self.truth_rows.append({
                "opportunity_id": opp_id,
                "account_id": acct["account_id"],
                "touch_position": tp["position"],
                "touch_ts": tp["ts"].isoformat(),
                "channel": tp["channel"],
                "latent_weight": round(tp["latent_weight"], 6),
                "true_credit_fraction": round(tp["latent_weight"] / tw, 6),
                "true_credit_arr_usd": round(arr * (tp["latent_weight"] / tw), 2),
                "was_tracked": (not tp.get("dropped", False)),
                "is_won": (won and not is_open),
            })

    def _fmt_date(self, dt, rng):
        if rng.random() < self.cfg["noise"]["mixed_date_format_rate"]:
            return dt.strftime("%d/%m/%Y")
        return dt.date().isoformat()

    # ---------------- run ---------------- #
    def run(self):
        n = self.cfg["volumes"]["n_accounts"]
        for i in range(n):
            acct = self.make_account(i)
            persons = self.make_persons(acct)
            touches, decision_dt, total_w, p_conv, converted = self.build_journey(acct, persons)
            self.emit_events(acct, touches)
            self.emit_crm(acct, persons, touches, converted, total_w, decision_dt)
            self.accounts.append(acct)
            self.persons.extend(persons)
            if (i + 1) % 1000 == 0:
                print(f"  ... {i+1}/{n} accounts")
        return self


# --------------------------------------------------------------------------- #
# writers
# --------------------------------------------------------------------------- #

def write_all(world: World, out_dir: str, truth_dir: str):
    import pandas as pd
    os.makedirs(f"{out_dir}/segment_events", exist_ok=True)
    os.makedirs(f"{out_dir}/salesforce", exist_ok=True)
    os.makedirs(f"{out_dir}/ad_platforms", exist_ok=True)
    os.makedirs(truth_dir, exist_ok=True)

    buckets = defaultdict(list)
    for e in world.events:
        buckets[e["timestamp"][:7]].append(e)
    for month, rows in sorted(buckets.items()):
        with open(f"{out_dir}/segment_events/events_{month}.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def dump(rows, path, drop=()):
        df = pd.DataFrame(rows)
        for c in drop:
            if c in df.columns:
                df = df.drop(columns=[c])
        df.to_csv(path, index=False)
        return len(df)

    counts = {
        "accounts":   dump(world.accounts, f"{out_dir}/salesforce/accounts.csv"),
        "leads":      dump(world.leads, f"{out_dir}/salesforce/leads.csv"),
        "contacts":   dump(world.contacts, f"{out_dir}/salesforce/contacts.csv"),
        "campaigns":  dump(list(world.campaigns.values()), f"{out_dir}/salesforce/campaigns.csv"),
        "campaign_members": dump(world.campaign_members, f"{out_dir}/salesforce/campaign_members.csv"),
        "opportunities": dump(world.opps, f"{out_dir}/salesforce/opportunities.csv"),
        "opportunity_stage_history": dump(world.stage_hist, f"{out_dir}/salesforce/opportunity_stage_history.csv"),
        "spend":      dump(world.spend_rows, f"{out_dir}/ad_platforms/spend.csv"),
        "events":     len(world.events),
    }

    truth = pd.DataFrame(world.truth_rows)
    truth.to_csv(f"{truth_dir}/account_touch_credit.csv", index=False)

    if len(truth):
        ch = (truth.groupby("channel")
                   .agg(true_credit_fraction=("true_credit_fraction", "sum"),
                        true_credit_arr_usd=("true_credit_arr_usd", "sum"),
                        touches=("channel", "size"))
                   .reset_index())
        ch["true_share_of_opps"] = ch["true_credit_fraction"] / ch["true_credit_fraction"].sum()
        ch["true_share_of_arr"] = ch["true_credit_arr_usd"] / ch["true_credit_arr_usd"].sum()
        ch["configured_true_effect"] = ch["channel"].map(
            {k: v["true_effect"] for k, v in world.channels.items()})
        ch.sort_values("true_share_of_arr", ascending=False).to_csv(
            f"{truth_dir}/channel_contribution.csv", index=False)

    manifest = {
        "generated_at": datetime.now().isoformat() + "Z",
        "seed": world.cfg["seed"],
        "date_range": [world.cfg["start_date"], world.cfg["end_date"]],
        "row_counts": counts,
        "opportunities_won": int(sum(1 for o in world.opps if o["is_won"])),
        "config_digest": hashlib.sha1(json.dumps(world.cfg, sort_keys=True).encode()).hexdigest(),
    }
    with open(f"{truth_dir}/run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/simulation.yml")
    ap.add_argument("--out", default="raw")
    ap.add_argument("--truth", default="ground_truth")
    ap.add_argument("--accounts", type=int, default=None, help="override n_accounts (for smoke tests)")
    a = ap.parse_args()

    cfg = yaml.safe_load(open(a.config))
    if a.accounts:
        cfg["volumes"]["n_accounts"] = a.accounts
    print(f"Simulating {cfg['volumes']['n_accounts']} accounts, seed={cfg['seed']} ...")
    w = World(cfg).run()
    m = write_all(w, a.out, a.truth)
    print(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
