import html

import streamlit as st

import lib
from nodi.messaging.sms import check_message

lib.page_setup("Campaign studio")
msgs, spec = lib.messages(), lib.messaging_spec()
segs = msgs[["segment_id", "segment"]].drop_duplicates().sort_values("segment_id")
default = st.session_state.get("studio_segment", 1)

c1, c2, c3 = st.columns([1.4, 1.2, 1])
sid = c1.selectbox("Segment", segs.segment_id, index=int(segs.segment_id.tolist().index(default)),
                   format_func=lambda i: f"{i}. {segs.set_index('segment_id').segment[i]}")
offers = msgs[msgs.segment_id == sid].offer_id.unique().tolist()
offer = c2.selectbox("Offer", offers, format_func=lambda o: lib.OFFER_LABEL[o])
lang = c3.radio("Language", ["bn", "en"], horizontal=True, format_func=lambda x: "বাংলা" if x == "bn" else "English")

sel = msgs[(msgs.segment_id == sid) & (msgs.offer_id == offer) & (msgs.lang == lang)].sort_values("variant")
o = spec["offers"][offer]
src = sel.source.iloc[0] if len(sel) else ""
if src != "api":
    st.warning("**Mock mode, seed copy.** These messages were written in a Claude Code session and assembled from "
               "per-segment openings, not produced by the API pipeline. Run `python run.py --only messages --live` "
               "with an API key to regenerate with claude-sonnet-5-5.", icon=":material/info:")
st.markdown(f'<p class="nodi-muted"><b>Offer record</b> (the only facts a message may use): {html.escape(o["facts"])}</p>',
            unsafe_allow_html=True)

cols = st.columns(3)
for col, (_, r) in zip(cols, sel.iterrows()):
    with col:
        st.markdown(f"**Variant {r.variant}**<br><span class='nodi-muted'>{html.escape(r.angle)}</span>",
                    unsafe_allow_html=True)
        st.markdown(f'<div class="nodi-phone">{html.escape(r.text)}</div>', unsafe_allow_html=True)
        ok = '<span class="nodi-tag nodi-ok">passes all checks</span>' if r.valid else \
            '<span class="nodi-tag nodi-bad">rejected</span>'
        st.markdown(f'{ok}<span class="nodi-tag">{r.parts} SMS part{"s" if r.parts > 1 else ""}</span>'
                    f'<span class="nodi-tag">{r.units} {r.encoding} chars</span>', unsafe_allow_html=True)
        if lang == "bn":
            with st.expander("English gloss"):
                st.write(r.english_gloss)

st.divider()
st.subheader("Try the validator")
st.markdown('<p class="nodi-muted">Edit a message the way a model might get it wrong (change a number, add '
            '"unlimited", drop the STOP line, write a number in words). The same checks gate every generated SMS.</p>',
            unsafe_allow_html=True)
text = st.text_area("SMS text", sel.text.iloc[0] if len(sel) else "", height=110, key=f"try-{sid}-{offer}-{lang}")
res = check_message(text, lang, o, spec)
if res.ok:
    st.success(f"Passes: {res.parts} SMS part(s), {res.units} {res.encoding} characters.", icon=":material/check_circle:")
else:
    st.error("Rejected:\n\n" + "\n".join(f"- {e}" for e in res.errors), icon=":material/block:")

with st.expander("SMS rules used"):
    st.markdown(
        f"- English must be GSM-7 and fit one SMS (160 characters). Bangla is Unicode (UCS-2): "
        f"70 characters in one SMS, 67 per part when longer; limit {spec['sms_limits']['bn']} parts.\n"
        f"- Allowed numbers for this offer: {o['numbers']} (must include {o['required']}); "
        f"dial code {o['dial_code'] or 'none'}; opt-out `{spec['optout']}`.\n"
        "- Brand voice and all offer facts live in messaging.yml; native-speaker review in review/bangla_review.csv.")
