# Phase 6: campaign SMS (synthetic data)

Mode: **mock**. Sources: {'seed-claude-code-session': 156}. 26 segment x offer cells, 156 messages, **156 pass every check**.

> **Seed copy.** These messages were written in a Claude Code session (claude-opus-5-5), assembled from per-segment openings and per-offer bodies, NOT produced by the API pipeline. Regenerate with `python run.py --only messages --live` once an API key is set.

| Language | Messages | Valid | SMS parts | Longest |
|---|---:|---:|---|---:|
| English | 78 | 78 | {1: 78} | 132 units |
| Bangla | 78 | 78 | {2: 78} | 130 units |

## The validator catches what a model might get wrong

| Planted mistake | Caught? | Validator says |
|---|---|---|
| Model invents a bigger allowance | yes | numbers not in the offer record: [3]; required offer numbers missing: [2] |
| Model invents a deadline | yes | numbers not in the offer record: [48] |
| Taka sign in English (forces Unicode) | yes | English must be GSM-7; non-GSM characters: ৳; 2 SMS parts (79 UCS-2 units); limit is 1 |
| Number in words | yes | required offer numbers missing: [2]; number written in words ('two'): use digits |
| Opt-out line missing | yes | must end with the opt-out line 'STOP: 21212' |
| Bangla too long (3 parts) | yes | 3 SMS parts (171 UCS-2 units); limit is 2 |
| Dial code in Bangla digits | yes | numbers not in the offer record: [121]; dial code *121*2# missing or altered (keep English digits) |
| Unlimited claim | yes | forbidden claim: 'আনলিমিটেড' |

## One example per segment (variant 1)

- **1. Fading high-value** · bonus_data · en (1 part, 85 GSM-7 units): We miss you at Nodi! 2 GB free data, valid 7 days. Dial *121*2# to claim. STOP: 21212
- **1. Fading high-value** · bonus_data · bn (2 parts, 89 UCS-2 units): নদী আপনাকে মিস করছে! ২ জিবি ফ্রি ডেটা, মেয়াদ ৭ দিন। পেতে ডায়াল করুন *121*2# STOP: 21212
- **2. Shaky newcomers** · bonus_data · en (1 part, 81 GSM-7 units): Welcome to Nodi! 2 GB free data, valid 7 days. Dial *121*2# to claim. STOP: 21212
- **2. Shaky newcomers** · bonus_data · bn (2 parts, 84 UCS-2 units): নদী-তে স্বাগতম! ২ জিবি ফ্রি ডেটা, মেয়াদ ৭ দিন। পেতে ডায়াল করুন *121*2# STOP: 21212
- **3. Slipping valuables** · bonus_data · en (1 part, 78 GSM-7 units): Just for you: 2 GB free data, valid 7 days. Dial *121*2# to claim. STOP: 21212
- **3. Slipping valuables** · bonus_data · bn (2 parts, 85 UCS-2 units): শুধু আপনার জন্য: ২ জিবি ফ্রি ডেটা, মেয়াদ ৭ দিন। পেতে ডায়াল করুন *121*2# STOP: 21212
- **4. Valuable but exposed** · bonus_data · en (1 part, 97 GSM-7 units): Thank you for staying with Nodi! 2 GB free data, valid 7 days. Dial *121*2# to claim. STOP: 21212
- **4. Valuable but exposed** · bonus_data · bn (2 parts, 99 UCS-2 units): নদী-র সাথে থাকার জন্য ধন্যবাদ! ২ জিবি ফ্রি ডেটা, মেয়াদ ৭ দিন। পেতে ডায়াল করুন *121*2# STOP: 21212
- **5. Mid-value gone quiet** · bonus_data · en (1 part, 93 GSM-7 units): Haven't seen you in a while! 2 GB free data, valid 7 days. Dial *121*2# to claim. STOP: 21212
- **5. Mid-value gone quiet** · bonus_data · bn (2 parts, 86 UCS-2 units): অনেকদিন দেখা নেই! ২ জিবি ফ্রি ডেটা, মেয়াদ ৭ দিন। পেতে ডায়াল করুন *121*2# STOP: 21212
- **6. Low-value lapsers** · reminder · en (1 part, 76 GSM-7 units): Nodi reminder: Data 1GB, 7 days, only Tk59. Dial *121*1# to buy. STOP: 21212
- **6. Low-value lapsers** · reminder · bn (2 parts, 90 UCS-2 units): নদী-র রিমাইন্ডার: ১ জিবি ডেটা, ৭ দিন, মাত্র ৫৯ টাকা। কিনতে ডায়াল করুন *121*1# STOP: 21212
- **7. Low-value wobblers** · reminder · en (1 part, 71 GSM-7 units): Nodi tip: Data 1GB, 7 days, only Tk59. Dial *121*1# to buy. STOP: 21212
- **7. Low-value wobblers** · reminder · bn (2 parts, 84 UCS-2 units): নদী-র টিপস: ১ জিবি ডেটা, ৭ দিন, মাত্র ৫৯ টাকা। কিনতে ডায়াল করুন *121*1# STOP: 21212
- **8. Stable core** · bonus_data · en (1 part, 90 GSM-7 units): A little extra from Nodi: 2 GB free data, valid 7 days. Dial *121*2# to claim. STOP: 21212
- **8. Stable core** · bonus_data · bn (2 parts, 97 UCS-2 units): নদী-র পক্ষ থেকে একটু বাড়তি: ২ জিবি ফ্রি ডেটা, মেয়াদ ৭ দিন। পেতে ডায়াল করুন *121*2# STOP: 21212
