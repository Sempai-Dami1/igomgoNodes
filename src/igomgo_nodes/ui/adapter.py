"""Transactional graph editing and conversion to the ready-made canvas."""

from collections.abc import Mapping
from html import escape
from urllib.parse import quote
from uuid import uuid4

from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState

from igomgo_nodes.core import Edge, Graph, GraphPolicy, NodeInstance, NodeRegistry, Position
from igomgo_nodes.core.unroll import MAX_EXPANDED_EDGES, MAX_EXPANDED_NODES

_FEEDBACK_BLUR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="10" y="17" width="32" height="32" rx="3" fill="#ec7da7"/>
<path d="M10 17h16v16H10zm16 16h16v16H26z" fill="#6ac694"/>
<path d="M42 33h14m-5-4 5 4-5 4M73 33h15m-5-4 5 4-5 4"
 fill="none" stroke="#5dd8cb" stroke-width="2"/>
<path d="M64 24l9 9-9 9-9-9z" fill="#384e5c" stroke="#5dd8cb"/>
<rect x="90" y="17" width="32" height="32" rx="4" fill="#bc9ca5"/>
<circle cx="98" cy="25" r="7" fill="#93b9a2" opacity=".8"/>
<circle cx="114" cy="41" r="7" fill="#93b9a2" opacity=".8"/>
<path d="M123 33h19v23H64V44m-4 5 4-5 4 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<path d="M143 33h16m-5-4 5 4-5 4" fill="none" stroke="#5dd8cb" stroke-width="2"/>
</svg>"""
_FEEDBACK_ECHO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="10" y="17" width="32" height="32" rx="3" fill="#30495a"/>
<path d="M13 33h3l2-9 4 18 4-21 4 18 3-10 2 4h4"
 fill="none" stroke="#ec7da7" stroke-width="2" stroke-linejoin="round"/>
<path d="M42 33h14m-5-4 5 4-5 4M73 33h15m-5-4 5 4-5 4"
 fill="none" stroke="#5dd8cb" stroke-width="2"/>
<path d="M64 24l9 9-9 9-9-9z" fill="#384e5c" stroke="#5dd8cb"/>
<path d="M60 33h8m-4-4v8" stroke="#5dd8cb" stroke-width="1.5"/>
<rect x="90" y="17" width="32" height="32" rx="4" fill="#30495a"/>
<path d="M93 33h2l2-9 3 18 3-16 3 14 3-11 3 8 3-6 2 4h2"
 fill="none" stroke="#6ac694" stroke-width="2" stroke-linejoin="round"/>
<path d="M123 33h19v23H64V44m-4 5 4-5 4 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<path d="M143 33h16m-5-4 5 4-5 4" fill="none" stroke="#5dd8cb" stroke-width="2"/>
</svg>"""
_WAV_INPUT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M22 14h27l10 10v34H22z" fill="#30495a" stroke="#9bb6c3" stroke-width="2"/>
<path d="M49 14v10h10M28 34h25M28 40h25M28 46h17" fill="none" stroke="#9bb6c3"
 stroke-width="2"/>
<path d="M68 36h27m-6-5 6 5-6 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="105" y="19" width="52" height="34" rx="4" fill="#30495a"/>
<path d="M109 36h5l3-10 5 20 5-24 5 25 5-18 4 14 4-10 3 3h5"
 fill="none" stroke="#ec7da7" stroke-width="2" stroke-linejoin="round"/>
</svg>"""
_WAV_OUTPUT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="12" y="19" width="48" height="34" rx="4" fill="#30495a"/>
<path d="M16 36h4l3-10 5 20 5-24 5 25 5-18 4 14 4-10 3 3h2"
 fill="none" stroke="#6ac694" stroke-width="2" stroke-linejoin="round"/>
<path d="M65 36h20m-6-5 6 5-6 5M90 36h7M97 36V21h9M97 36v15h9"
 fill="none" stroke="#5dd8cb" stroke-width="2"/>
<path d="M111 17h7l8-6v20l-8-6h-7z" fill="#9bb6c3"/>
<path d="M130 17c3 2 3 6 0 8m4-12c6 4 6 12 0 16"
 fill="none" stroke="#9bb6c3" stroke-width="2" stroke-linecap="round"/>
<path d="M110 39h20l7 7v17h-27z" fill="#30495a" stroke="#9bb6c3" stroke-width="2"/>
<path d="M130 39v7h7m-22 5h16m-16 5h16" fill="none" stroke="#9bb6c3" stroke-width="2"/>
</svg>"""
_AUDIO_GAIN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="10" y="20" width="44" height="32" rx="4" fill="#30495a"/>
<path d="M14 36h4l3-4 4 8 4-7 4 6 4-3h5" fill="none" stroke="#9bb6c3"
 stroke-width="2" stroke-linejoin="round"/>
<path d="M57 36h13m-5-5 5 5-5 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<path d="M78 52V20l39 16z" fill="#30495a" stroke="#6ac694" stroke-width="2"/>
<text x="91" y="39" text-anchor="middle" fill="#9bb6c3" font-family="sans-serif"
 font-size="10">+</text>
<path d="M87 44h8" stroke="#9bb6c3" stroke-width="1.5"/>
<path d="M118 36h10m-5-5 5 5-5 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="132" y="20" width="38" height="32" rx="4" fill="#30495a"/>
<path d="M136 36h3l4-11 5 22 5-27 5 28 5-14 3 2h2" fill="none" stroke="#ec7da7"
 stroke-width="2" stroke-linejoin="round"/>
</svg>"""
_AUDIO_LOWPASS_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="10" y="20" width="46" height="32" rx="4" fill="#30495a"/>
<path d="M13 36h3l3-10 4 20 4-20 4 20 4-20 4 20 4-10h5" fill="none"
 stroke="#ec7da7" stroke-width="2" stroke-linejoin="round"/>
<path d="M58 36h13m-5-5 5 5-5 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="74" y="16" width="42" height="40" rx="4" fill="#30495a" stroke="#9bb6c3"/>
<path d="M82 48V24m0 24h27M84 28c6 0 8 1 11 5s5 10 12 11"
 fill="none" stroke="#6ac694" stroke-width="2"/>
<path d="M118 36h10m-5-5 5 5-5 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="132" y="20" width="38" height="32" rx="4" fill="#30495a"/>
<path d="M136 36h3l4-8 5 16 5-13 5 10 5-6 3 1h2" fill="none" stroke="#6ac694"
 stroke-width="2" stroke-linejoin="round"/>
</svg>"""
_AUDIO_DELAY_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="10" y="19" width="40" height="34" rx="4" fill="#30495a"/>
<path d="M14 36h4l3-10 5 20 5-24 5 25 4-12 3 1h3" fill="none" stroke="#ec7da7"
 stroke-width="2" stroke-linejoin="round"/>
<path d="M51 36h11m-5-5 5 5-5 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="64" y="23" width="36" height="26" rx="4" fill="#30495a" stroke="#9bb6c3"/>
<path d="M70 36h5l4-7 5 14 5-14 5 7h3" fill="none" stroke="#6ac694" stroke-width="2"/>
<path d="M101 36h10m-5-5 5 5-5 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<path d="M113 36h5l4-7 5 14 5-14 5 7h3m-22 0h5l4-5 5 10 5-10 5 5h3"
 fill="none" stroke="#ec7da7" stroke-width="2" stroke-linejoin="round"/>
<path d="M89 50v11H27V54m-4 4 4-4 4 4" fill="none" stroke="#5dd8cb" stroke-width="1.5"/>
</svg>"""
_IMAGE_INPUT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M22 14h27l10 10v34H22z" fill="#30495a" stroke="#9bb6c3" stroke-width="2"/>
<path d="M49 14v10h10" fill="none" stroke="#9bb6c3" stroke-width="2"/>
<circle cx="33" cy="33" r="3" fill="#ec7da7"/>
<path d="M27 50l9-10 5 5 5-7 8 12z" fill="#6ac694"/>
<path d="M68 36h27m-6-5 6 5-6 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="105" y="19" width="40" height="34" rx="3" fill="#ec7da7"/>
<path d="M105 19h20v17h-20zm20 17h20v17h-20z" fill="#6ac694"/>
</svg>"""
_IMAGE_OUTPUT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="12" y="19" width="40" height="34" rx="3" fill="#ec7da7"/>
<path d="M12 19h20v17H12zm20 17h20v17H32z" fill="#6ac694"/>
<path d="M60 36h25m-6-5 6 5-6 5M90 36h7M97 36V21h9M97 36v15h9"
 fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="110" y="10" width="32" height="22" rx="2" fill="#30495a" stroke="#9bb6c3"/>
<circle cx="119" cy="17" r="2" fill="#ec7da7"/>
<path d="M113 28l7-7 5 4 5-5 9 8z" fill="#6ac694"/>
<path d="M110 39h20l7 7v17h-27z" fill="#30495a" stroke="#9bb6c3" stroke-width="2"/>
<path d="M130 39v7h7m-22 5h16m-16 5h16" fill="none" stroke="#9bb6c3" stroke-width="2"/>
</svg>"""
_IMAGE_GRAYSCALE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="10" y="20" width="42" height="32" rx="3" fill="#30495a"/>
<path d="M14 24h10v10H14z" fill="#ec7da7"/><path d="M25 24h11v10H25z" fill="#6ac694"/>
<path d="M37 24h11v10H37z" fill="#5dd8cb"/><path d="M14 35h10v13H14z" fill="#6ac694"/>
<path d="M25 35h11v13H25z" fill="#5dd8cb"/><path d="M37 35h11v13H37z" fill="#ec7da7"/>
<path d="M55 36h27m-6-5 6 5-6 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<path d="M91 36h7m-4-4 4 4-4 4" fill="none" stroke="#9bb6c3" stroke-width="2"/>
<rect x="106" y="20" width="42" height="32" rx="3" fill="#30495a"/>
<path d="M110 24h10v10h-10z" fill="#d9e0e3"/><path d="M121 24h11v10h-11z" fill="#9bb6c3"/>
<path d="M133 24h11v10h-11z" fill="#52616a"/><path d="M110 35h10v13h-10z" fill="#9bb6c3"/>
<path d="M121 35h11v13h-11z" fill="#52616a"/><path d="M133 35h11v13h-11z" fill="#d9e0e3"/>
</svg>"""
_IMAGE_BLUR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="10" y="20" width="40" height="32" rx="3" fill="#30495a"/>
<path d="M13 23h12v12H13zM26 23h11v12H26zM38 23h9v12h-9zM13 36h12v13H13z"
 fill="#ec7da7"/>
<path d="M26 36h11v13H26zM38 36h9v13h-9z" fill="#6ac694"/>
<path d="M53 36h13m-5-5 5 5-5 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<circle cx="87" cy="36" r="18" fill="#30495a" stroke="#9bb6c3" stroke-width="2"/>
<circle cx="87" cy="36" r="11" fill="#6ac694" opacity=".55"/>
<circle cx="87" cy="36" r="5" fill="#ec7da7" opacity=".8"/>
<path d="M107 36h13m-5-5 5 5-5 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="126" y="20" width="44" height="32" rx="3" fill="#30495a"/>
<circle cx="141" cy="34" r="10" fill="#ec7da7" opacity=".7"/>
<circle cx="155" cy="39" r="10" fill="#6ac694" opacity=".65"/>
</svg>"""
_IMAGE_INVERT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="10" y="20" width="40" height="32" rx="3" fill="#30495a"/>
<path d="M13 23h11v13H13z" fill="#ec7da7"/><path d="M25 23h10v13H25z" fill="#6ac694"/>
<path d="M36 23h11v13H36z" fill="#5dd8cb"/><path d="M13 37h11v12H13z" fill="#6ac694"/>
<path d="M25 37h10v12H25z" fill="#5dd8cb"/><path d="M36 37h11v12H36z" fill="#ec7da7"/>
<path d="M53 36h13m-5-5 5 5-5 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<circle cx="88" cy="36" r="17" fill="#30495a" stroke="#9bb6c3" stroke-width="2"/>
<path d="M88 19a17 17 0 0 0 0 34z" fill="#ec7da7"/>
<path d="M88 19a17 17 0 0 1 0 34z" fill="#6ac694"/>
<path d="M108 36h12m-5-5 5 5-5 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="126" y="20" width="44" height="32" rx="3" fill="#30495a"/>
<path d="M129 23h11v13h-11z" fill="#13a058"/><path d="M141 23h10v13h-10z" fill="#9e684c"/>
<path d="M152 23h15v13h-15z" fill="#a22a47"/><path d="M129 37h11v12h-11z" fill="#9e684c"/>
<path d="M141 37h10v12h-10z" fill="#a22a47"/><path d="M152 37h15v12h-15z" fill="#13a058"/>
</svg>"""
_LOGIC_INPUT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<text x="24" y="26" text-anchor="middle" fill="#9bb6c3" font-family="sans-serif"
 font-size="10">0</text>
<text x="54" y="26" text-anchor="middle" fill="#9bb6c3" font-family="sans-serif"
 font-size="10">1</text>
<path d="M14 41h18m12 0h19" fill="none" stroke="#9bb6c3" stroke-width="2"/>
<rect x="29" y="33" width="18" height="16" rx="8" fill="#30495a" stroke="#5dd8cb"
 stroke-width="2"/>
<circle cx="40" cy="41" r="5" fill="#6ac694"/>
<path d="M64 41h29m-6-5 6 5-6 5M98 41h39" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<circle cx="145" cy="41" r="8" fill="#6ac694"/>
</svg>"""
_LOGIC_NOT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M16 36h45m-7-5 7 5-7 5" fill="none" stroke="#9bb6c3" stroke-width="2"/>
<path d="M65 19v34l44-17z" fill="#30495a" stroke="#6ac694" stroke-width="2"/>
<circle cx="117" cy="36" r="7" fill="#192633" stroke="#ec7da7" stroke-width="2"/>
<path d="M124 36h37m-7-5 7 5-7 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
</svg>"""
_LOGIC_AND_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M14 27h48m-7-5 7 5-7 5M14 45h48m-7-5 7 5-7 5"
 fill="none" stroke="#9bb6c3" stroke-width="2"/>
<path d="M67 18h25a18 18 0 0 1 0 36H67z" fill="#30495a" stroke="#6ac694" stroke-width="2"/>
<path d="M110 36h49m-7-5 7 5-7 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
</svg>"""
_LOGIC_OR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M13 26c19 0 29 3 48 10-19 7-29 10-48 10m0-20 8 10-8 10"
 fill="none" stroke="#9bb6c3" stroke-width="2"/>
<path d="M63 18c20 0 31 5 48 18-17 13-28 18-48 18 10-12 10-24 0-36z"
 fill="#30495a" stroke="#6ac694" stroke-width="2"/>
<path d="M111 36h48m-7-5 7 5-7 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
</svg>"""
_LOGIC_XOR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M7 18c10 12 10 24 0 36M17 26c19 0 29 3 48 10-19 7-29 10-48 10m0-20 8 10-8 10"
 fill="none" stroke="#9bb6c3" stroke-width="2"/>
<path d="M67 18c20 0 31 5 48 18-17 13-28 18-48 18 10-12 10-24 0-36z"
 fill="#30495a" stroke="#6ac694" stroke-width="2"/>
<path d="M115 36h44m-7-5 7 5-7 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
</svg>"""
_LOGIC_OUTPUT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M17 36h37m-7-5 7 5-7 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<circle cx="91" cy="36" r="24" fill="#30495a" stroke="#9bb6c3" stroke-width="2"/>
<path d="M82 34a9 9 0 1 1 18 0c0 4-3 5-3 9h-12c0-4-3-5-3-9z"
 fill="#6ac694" stroke="#5dd8cb" stroke-width="1.5"/>
<path d="M85 47h12m-10 4h8M117 36h45m-7-5 7 5-7 5"
 fill="none" stroke="#9bb6c3" stroke-width="2"/>
</svg>"""
_LOGIC_FEEDBACK_NOT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M14 28h36m-7-5 7 5-7 5" fill="none" stroke="#9bb6c3" stroke-width="2"/>
<path d="M53 17v22l29-11z" fill="#30495a" stroke="#6ac694" stroke-width="2"/>
<circle cx="88" cy="28" r="6" fill="#192633" stroke="#ec7da7" stroke-width="2"/>
<path d="M94 28h34m-7-5 7 5-7 5M128 28v31H31V34"
 fill="none" stroke="#5dd8cb" stroke-width="2"/>
<path d="M27 39l4-5 4 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<circle cx="128" cy="28" r="2" fill="#5dd8cb"/>
</svg>"""
_SQUARE_ROOT_FEEDBACK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M42 8v36l34-18z" fill="#30495a" stroke="#9bb6c3" stroke-width="2"/>
<path d="M10 17h32m34 9h86m-6-5 6 5-6 5"
 fill="none" stroke="#5dd8cb" stroke-width="2"/>
<path d="M47 16h6m-3-3v6m-3 15h6" stroke="#9bb6c3" stroke-width="1.5"/>
<rect x="100" y="43" width="25" height="20" rx="2" fill="#30495a" stroke="#9bb6c3"/>
<path d="M108 48l9 10m0-10-9 10" stroke="#ec7da7" stroke-width="2"/>
<path d="M135 26v22h-10m18-22v29h-18M100 53H31V36h11"
 fill="none" stroke="#5dd8cb" stroke-width="2"/>
<circle cx="135" cy="26" r="2" fill="#5dd8cb"/>
<circle cx="143" cy="26" r="2" fill="#5dd8cb"/>
</svg>"""
_ELECTRONICS_SUPPLY_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<rect x="12" y="13" width="52" height="46" rx="4" fill="#30495a"/>
<text x="38" y="25" text-anchor="middle" fill="#9bb6c3" font-family="sans-serif"
 font-size="10">AC</text>
<path d="M20 42c5-14 10-14 15 0s10 14 15 0 5-14 7-14"
 fill="none" stroke="#ec7da7" stroke-width="2"/>
<rect x="72" y="13" width="52" height="46" rx="4" fill="#30495a"/>
<text x="98" y="25" text-anchor="middle" fill="#9bb6c3" font-family="sans-serif"
 font-size="10">DC</text>
<path d="M81 36h34m-34 7h6m4 0h6m4 0h6m4 0h4"
 fill="none" stroke="#6ac694" stroke-width="2"/>
<path d="M130 36h29m-6-5 6 5-6 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
</svg>"""
_ELECTRONICS_LED_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M19 39h35m-6-5 6 5-6 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<circle cx="91" cy="39" r="23" fill="#30495a" stroke="#9bb6c3" stroke-width="2"/>
<path d="M63 40h14m0-10v20l19-10zm19-10v20m0-10h22"
 fill="none" stroke="#6ac694" stroke-width="2" stroke-linejoin="round"/>
<path d="M102 20l9-8m-1 5 1-5-5 1M112 26l9-8m-1 5 1-5-5 1"
 fill="none" stroke="#ec7da7" stroke-width="2" stroke-linecap="round"/>
</svg>"""
_ELECTRONICS_RESISTOR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M12 36h34m88 0h34" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="46" y="21" width="88" height="30" rx="4" fill="#30495a" stroke="#9bb6c3"
 stroke-width="2"/>
<path d="M52 36h8l6-9 10 18 10-18 10 18 10-18 10 18 8-9h4"
 fill="none" stroke="#ec7da7" stroke-width="2.5" stroke-linejoin="round"/>
<circle cx="12" cy="36" r="2" fill="#9bb6c3"/><circle cx="168" cy="36" r="2" fill="#9bb6c3"/>
</svg>"""
_ELECTRONICS_NUMBER_INPUT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M15 36h26m-6-5 6 5-6 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="45" y="15" width="84" height="42" rx="5" fill="#30495a" stroke="#9bb6c3"
 stroke-width="2"/>
<text x="87" y="43" text-anchor="middle" fill="#6ac694" font-family="monospace"
 font-size="24">9</text>
<path d="M129 36h37m-7-5 7 5-7 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
</svg>"""
_ELECTRONICS_SQRT_OUTPUT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 72">
<rect x="1" y="1" width="178" height="70" rx="8" fill="#192633" stroke="#4c6575"/>
<path d="M14 38h9l5 11 11-27h22" fill="none" stroke="#6ac694" stroke-width="3"
 stroke-linejoin="round"/>
<path d="M66 36h19m-6-5 6 5-6 5" fill="none" stroke="#5dd8cb" stroke-width="2"/>
<rect x="90" y="17" width="66" height="38" rx="4" fill="#30495a" stroke="#9bb6c3"
 stroke-width="2"/>
<text x="123" y="42" text-anchor="middle" fill="#ec7da7" font-family="monospace"
 font-size="18">3.0</text>
<path d="M158 36h12" fill="none" stroke="#5dd8cb" stroke-width="2"/>
</svg>"""
_BUILTIN_ICONS = {
    "feedback-blur": f'url("data:image/svg+xml,{quote(_FEEDBACK_BLUR_SVG)}")',
    "feedback-echo": f'url("data:image/svg+xml,{quote(_FEEDBACK_ECHO_SVG)}")',
    "wav-input": f'url("data:image/svg+xml,{quote(_WAV_INPUT_SVG)}")',
    "wav-output": f'url("data:image/svg+xml,{quote(_WAV_OUTPUT_SVG)}")',
    "audio-gain": f'url("data:image/svg+xml,{quote(_AUDIO_GAIN_SVG)}")',
    "audio-lowpass": f'url("data:image/svg+xml,{quote(_AUDIO_LOWPASS_SVG)}")',
    "audio-delay": f'url("data:image/svg+xml,{quote(_AUDIO_DELAY_SVG)}")',
    "image-input": f'url("data:image/svg+xml,{quote(_IMAGE_INPUT_SVG)}")',
    "image-output": f'url("data:image/svg+xml,{quote(_IMAGE_OUTPUT_SVG)}")',
    "image-grayscale": f'url("data:image/svg+xml,{quote(_IMAGE_GRAYSCALE_SVG)}")',
    "image-blur": f'url("data:image/svg+xml,{quote(_IMAGE_BLUR_SVG)}")',
    "image-invert": f'url("data:image/svg+xml,{quote(_IMAGE_INVERT_SVG)}")',
    "logic-input": f'url("data:image/svg+xml,{quote(_LOGIC_INPUT_SVG)}")',
    "logic-not": f'url("data:image/svg+xml,{quote(_LOGIC_NOT_SVG)}")',
    "logic-and": f'url("data:image/svg+xml,{quote(_LOGIC_AND_SVG)}")',
    "logic-or": f'url("data:image/svg+xml,{quote(_LOGIC_OR_SVG)}")',
    "logic-xor": f'url("data:image/svg+xml,{quote(_LOGIC_XOR_SVG)}")',
    "logic-output": f'url("data:image/svg+xml,{quote(_LOGIC_OUTPUT_SVG)}")',
    "logic-feedback-not": f'url("data:image/svg+xml,{quote(_LOGIC_FEEDBACK_NOT_SVG)}")',
    "square-root-feedback": f'url("data:image/svg+xml,{quote(_SQUARE_ROOT_FEEDBACK_SVG)}")',
    "electronics-supply": f'url("data:image/svg+xml,{quote(_ELECTRONICS_SUPPLY_SVG)}")',
    "electronics-led": f'url("data:image/svg+xml,{quote(_ELECTRONICS_LED_SVG)}")',
    "electronics-resistor": f'url("data:image/svg+xml,{quote(_ELECTRONICS_RESISTOR_SVG)}")',
    "electronics-number-input": f'url("data:image/svg+xml,{quote(_ELECTRONICS_NUMBER_INPUT_SVG)}")',
    "electronics-sqrt-output": f'url("data:image/svg+xml,{quote(_ELECTRONICS_SQRT_OUTPUT_SVG)}")',
}


class EditorAdapter:
    def __init__(self, graph: Graph, registry: NodeRegistry) -> None:
        self.registry = registry
        self.graph = graph
        self.selected_id: str | None = None
        self.selected_edge_id: str | None = None
        self.feedback_edge_ids: frozenset[str] = frozenset()
        self.revision = 0
        self.notice: tuple[str, str] | None = None
        self._validate(graph)
        self.flow_state = self._to_flow()

    def _validate(self, graph: Graph) -> None:
        if len(graph.nodes) > MAX_EXPANDED_NODES or len(graph.edges) > MAX_EXPANDED_EDGES:
            raise ValueError("Editor graph exceeds the node or edge limit")
        graph.validate_connections(self.registry, require_minimums=False)
        graph.validate_feedback()

    def _to_flow(self) -> StreamlitFlowState:
        edge_ids = {edge_id: canvas_id for canvas_id, edge_id in self._canvas_edge_ids().items()}
        nodes: list[StreamlitFlowNode] = []
        for node in self.graph.nodes:
            spec = self.registry.resolve(node.type_id).spec
            icon = _BUILTIN_ICONS.get(spec.icon)
            style: dict[str, object] = {}
            if icon:
                style.update(
                    {
                        "backgroundImage": icon,
                        "backgroundRepeat": "no-repeat",
                        "backgroundPosition": "center 8px",
                        "backgroundSize": "180px 72px",
                        "paddingTop": 86,
                        "minWidth": 200,
                    }
                )
            if node.node_id == self.selected_id:
                style["border"] = "2px solid red"
            nodes.append(
                StreamlitFlowNode(
                    node.node_id,
                    (node.position.x, node.position.y),
                    {"content": escape(f"{'' if icon else spec.icon} {spec.title}".strip())},
                    node_type="default"
                    if spec.inputs and spec.outputs
                    else ("input" if spec.outputs else "output"),
                    source_position="right",
                    target_position="left",
                    selectable=True,
                    selected=node.node_id == self.selected_id,
                    connectable=bool(spec.inputs or spec.outputs),
                    deletable=False,
                    style=style,
                )
            )
        edges = [
            StreamlitFlowEdge(
                edge_ids[edge.edge_id],
                edge.src_node,
                edge.dst_node,
                label=f"{edge.src_port} -> {edge.dst_port}",
                animated=edge.edge_id in self.feedback_edge_ids,
                selected=edge.edge_id == self.selected_edge_id,
                deletable=False,
                style={"stroke": "red", "strokeWidth": 3}
                if edge.edge_id == self.selected_edge_id
                else {},
            )
            for edge in self.graph.edges
        ]
        state = StreamlitFlowState(nodes, edges)
        if self.selected_id is not None:
            state.selected_id = self.selected_id
        elif self.selected_edge_id is not None:
            state.selected_id = edge_ids[self.selected_edge_id]
        return state

    def _canvas_edge_ids(self) -> dict[str, str]:
        node_ids = {node.node_id for node in self.graph.nodes}
        edge_ids = {edge.edge_id for edge in self.graph.edges}
        prefix = "edge:"
        while any(
            node_id.startswith(prefix) and node_id[len(prefix) :] in edge_ids
            for node_id in node_ids
        ):
            prefix = "edge:" + prefix
        return {prefix + edge.edge_id: edge.edge_id for edge in self.graph.edges}

    def refresh_canvas(self) -> None:
        self.revision += 1
        self.flow_state = self._to_flow()

    def _commit(
        self,
        nodes: tuple[NodeInstance, ...],
        edges: tuple[Edge, ...],
        policy: GraphPolicy | None = None,
    ) -> None:
        candidate = Graph(nodes=nodes, edges=edges, policy=policy or self.graph.policy)
        self._validate(candidate)
        self.graph = candidate
        if self.selected_id not in {node.node_id for node in nodes}:
            self.selected_id = None
        if self.selected_edge_id not in {edge.edge_id for edge in edges}:
            self.selected_edge_id = None
        self.feedback_edge_ids &= frozenset(edge.edge_id for edge in edges)
        self.refresh_canvas()

    def add_node(self, type_id: str, params: Mapping[str, object] | None = None) -> None:
        node_type = self.registry.resolve(type_id)
        params = node_type.validate_params(params if params is not None else {})
        node = NodeInstance(
            node_id=uuid4().hex,
            type_id=type_id,
            params=params,
            position=Position(x=80 + len(self.graph.nodes) * 40, y=180),
        )
        self._commit((*self.graph.nodes, node), self.graph.edges)
        self.select_node(node.node_id)

    def select_node(self, node_id: str | None) -> None:
        if node_id is not None and node_id not in {node.node_id for node in self.graph.nodes}:
            raise ValueError(f"Unknown node: {node_id}")
        self.selected_id = node_id
        self.selected_edge_id = None
        self.refresh_canvas()

    def remove_node(self, node_id: str) -> None:
        self.node(node_id)
        self._commit(
            tuple(node for node in self.graph.nodes if node.node_id != node_id),
            tuple(
                edge for edge in self.graph.edges if node_id not in (edge.src_node, edge.dst_node)
            ),
        )

    def node(self, node_id: str) -> NodeInstance:
        for node in self.graph.nodes:
            if node.node_id == node_id:
                return node
        raise ValueError(f"Unknown node: {node_id}")

    def move_node(self, node_id: str, position: Position) -> None:
        self.node(node_id)
        self._commit(
            tuple(
                node.model_copy(update={"position": position}) if node.node_id == node_id else node
                for node in self.graph.nodes
            ),
            self.graph.edges,
        )

    def update_params(self, node_id: str, params: Mapping[str, object]) -> None:
        node = self.node(node_id)
        validated = self.registry.resolve(node.type_id).validate_params(params)
        self._commit(
            tuple(
                item.model_copy(deep=True, update={"params": validated})
                if item.node_id == node_id
                else item
                for item in self.graph.nodes
            ),
            self.graph.edges,
        )

    def connect(self, src_node: str, src_port: str, dst_node: str, dst_port: str) -> None:
        edge = Edge(
            edge_id=uuid4().hex,
            src_node=src_node,
            src_port=src_port,
            dst_node=dst_node,
            dst_port=dst_port,
        )
        self._commit(self.graph.nodes, (*self.graph.edges, edge))

    def disconnect(self, edge_id: str) -> None:
        if edge_id not in {edge.edge_id for edge in self.graph.edges}:
            raise ValueError(f"Unknown edge: {edge_id}")
        self._commit(
            self.graph.nodes, tuple(edge for edge in self.graph.edges if edge.edge_id != edge_id)
        )

    def set_policy(self, policy: GraphPolicy) -> None:
        self._commit(self.graph.nodes, self.graph.edges, policy)

    def set_feedback_edges(self, edge_ids: frozenset[str]) -> None:
        self.graph.unroll(feedback_edge_ids=edge_ids)
        self.feedback_edge_ids = edge_ids
        self.refresh_canvas()

    def replace_graph(self, graph: Graph, feedback_edge_ids: frozenset[str] = frozenset()) -> None:
        self._validate(graph)
        for node in graph.nodes:
            self.registry.resolve(node.type_id).validate_params(node.params)
        edge_ids = frozenset(edge.edge_id for edge in graph.edges)
        if not feedback_edge_ids <= edge_ids:
            raise ValueError("Feedback edge IDs must reference edges in the graph")
        if feedback_edge_ids:
            graph.unroll(feedback_edge_ids=feedback_edge_ids)
        self.graph = graph
        self.selected_id = None
        self.selected_edge_id = None
        self.feedback_edge_ids = feedback_edge_ids
        self.notice = None
        self.refresh_canvas()

    def accept_canvas(self, state: StreamlitFlowState) -> None:
        originals = {node.node_id: node for node in self.graph.nodes}
        if any(node.id not in originals for node in state.nodes):
            raise ValueError("Add nodes from the palette, not the canvas menu")
        nodes = tuple(
            originals[node.id].model_copy(
                update={"position": Position.model_validate(node.position)}
            )
            for node in state.nodes
        )
        edges_by_id = {edge.edge_id: edge for edge in self.graph.edges}
        existing_edges = {
            canvas_id: edges_by_id[edge_id]
            for canvas_id, edge_id in self._canvas_edge_ids().items()
        }
        edges: list[Edge] = []
        added_edge_ids: set[str] = set()
        for edge in state.edges:
            if edge.id in existing_edges:
                original = existing_edges[edge.id]
                if (original.src_node, original.dst_node) != (edge.source, edge.target):
                    raise ValueError("Reconnect named ports using the Connections panel")
                edges.append(original)
            else:
                if edge.source not in originals or edge.target not in originals:
                    raise ValueError("Connection references an unknown node")
                source = self.registry.resolve(originals[edge.source].type_id).spec
                target = self.registry.resolve(originals[edge.target].type_id).spec
                if len(source.outputs) != 1 or len(target.inputs) != 1:
                    raise ValueError("Choose named ports in Connections for multi-port nodes")
                edges.append(
                    Edge(
                        edge_id=edge.id,
                        src_node=edge.source,
                        src_port=source.outputs[0].name,
                        dst_node=edge.target,
                        dst_port=target.inputs[0].name,
                    )
                )
                added_edge_ids.add(edge.id)
        candidate = Graph(nodes=nodes, edges=tuple(edges), policy=self.graph.policy)
        self._validate(candidate)
        structure_changed = candidate.edges != self.graph.edges or (
            tuple(node.node_id for node in candidate.nodes)
            != tuple(node.node_id for node in self.graph.nodes)
        )
        if candidate != self.graph:
            self.notice = None
        self.graph = candidate
        node_ids = {node.node_id for node in nodes}
        edge_ids = {edge.edge_id for edge in edges}
        previous_selection = (self.selected_id, self.selected_edge_id)
        # Drag-stop and pane-click both return selectedId=None in this component.
        if state.selected_id not in added_edge_ids:
            if state.selected_id in node_ids:
                self.selected_id = state.selected_id
                self.selected_edge_id = None
            elif state.selected_id in existing_edges:
                self.selected_id = None
                self.selected_edge_id = existing_edges[state.selected_id].edge_id
        if self.selected_id not in node_ids:
            self.selected_id = None
        if self.selected_edge_id not in edge_ids:
            self.selected_edge_id = None
        self.feedback_edge_ids &= frozenset(edge.edge_id for edge in edges)
        self.flow_state = state
        if structure_changed:
            self.refresh_canvas()
        elif previous_selection != (self.selected_id, self.selected_edge_id):
            self.flow_state = self._to_flow()
            # The component rejects updates older than its browser-side event timestamp.
            self.flow_state.timestamp = max(self.flow_state.timestamp, state.timestamp + 1)
