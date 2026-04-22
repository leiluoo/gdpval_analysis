#!/usr/bin/env python3
"""Generate pipeline flowchart as PNG."""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from matplotlib.patches import FancyArrowPatch
import matplotlib.patheffects as pe

plt.rcParams['font.sans-serif'] = ['STHeiti', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(figsize=(13, 20))
ax.set_xlim(0, 13)
ax.set_ylim(0, 20)
ax.axis('off')
fig.patch.set_facecolor('#FAFAFA')

# ── Palette ──────────────────────────────────────────────────────────────────
C_DATA      = '#D6EAF8';  B_DATA      = '#2980B9'
C_PROC      = '#D5F5E3';  B_PROC      = '#27AE60'
C_DEC       = '#FEF9E7';  B_DEC       = '#F39C12'
C_SAND      = '#F4ECF7';  B_SAND      = '#8E44AD'
C_TRAIN     = '#FADBD8';  B_TRAIN     = '#E74C3C'
C_FILE      = '#EBF5FB';  B_FILE      = '#5DADE2'
C_PHASE     = '#ECF0F1';  B_PHASE     = '#7F8C8D'
ARROW_C     = '#2C3E50'

# ── Helper: rounded box ───────────────────────────────────────────────────────
def box(x, y, w, h, lines, fc, ec, fs=9.5, bold_first=False, pad=0.15):
    patch = FancyBboxPatch(
        (x - w/2, y - h/2), w, h,
        boxstyle=f"round,pad={pad}",
        facecolor=fc, edgecolor=ec, linewidth=1.8, zorder=3
    )
    ax.add_patch(patch)
    if isinstance(lines, str):
        lines = [lines]
    n = len(lines)
    for i, line in enumerate(lines):
        dy = (n - 1) / 2 * 0.28 - i * 0.28
        w_ = 'bold' if (bold_first and i == 0) else 'normal'
        ax.text(x, y + dy, line, ha='center', va='center',
                fontsize=fs, fontweight=w_, zorder=4,
                color='#1A1A2E')

# ── Helper: diamond ───────────────────────────────────────────────────────────
def diamond(x, y, w, h, lines, fc, ec, fs=8.8):
    pts = [[x, y+h/2], [x+w/2, y], [x, y-h/2], [x-w/2, y]]
    poly = plt.Polygon(pts, facecolor=fc, edgecolor=ec, linewidth=1.8, zorder=3)
    ax.add_patch(poly)
    if isinstance(lines, str):
        lines = [lines]
    n = len(lines)
    for i, line in enumerate(lines):
        dy = (n-1)/2*0.22 - i*0.22
        ax.text(x, y + dy, line, ha='center', va='center',
                fontsize=fs, zorder=4, color='#1A1A2E')

# ── Helper: arrow ─────────────────────────────────────────────────────────────
def arrow(x1, y1, x2, y2, label='', label_dx=0.15, label_dy=0):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=ARROW_C,
                                lw=1.6, mutation_scale=16),
                zorder=5)
    if label:
        mx = (x1+x2)/2 + label_dx
        my = (y1+y2)/2 + label_dy
        ax.text(mx, my, label, fontsize=8, color='#555555',
                ha='left', va='center', zorder=6)

def harrow(x1, y1, x2, y2):
    """L-shaped arrow: horizontal then vertical."""
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=ARROW_C,
                                lw=1.5, mutation_scale=14,
                                connectionstyle='angle,angleA=0,angleB=90'),
                zorder=5)

# ── Phase banner ──────────────────────────────────────────────────────────────
def phase_banner(y, text, color='#D5D8DC'):
    rect = FancyBboxPatch((0.3, y - 0.22), 12.4, 0.44,
                           boxstyle="round,pad=0.05",
                           facecolor=color, edgecolor='#AAB7B8',
                           linewidth=1, zorder=2)
    ax.add_patch(rect)
    ax.text(6.5, y, text, ha='center', va='center',
            fontsize=10, fontweight='bold', color='#2C3E50', zorder=3)

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 BANNER
phase_banner(19.35, '① 任务生成阶段  build_prompt.py', '#D4E6F1')

# DATA SOURCES
box(3.4,  18.2, 3.6, 0.9,
    ['task_statements.jsonl', '923 职业角色 × 平均 20 条任务陈述'],
    C_DATA, B_DATA, fs=8.8, bold_first=True)

box(9.6,  18.2, 3.6, 0.9,
    ['train_filtered.jsonl', '95 参考任务 (prompt + rubric)'],
    C_DATA, B_DATA, fs=8.8, bold_first=True)

# merge arrows → sample box
arrow(3.4, 17.75, 4.9, 17.1)
arrow(9.6, 17.75, 8.1, 17.1)

# SAMPLE
box(6.5, 16.7, 4.5, 0.95,
    ['随机采样种子',
     'role  ×  task_statement  ×  output_format',
     '格式权重: docx 36% / pdf 34% / xlsx 16% / pptx 12% / zip 3%'],
    C_PROC, B_PROC, fs=8.5, bold_first=True)

arrow(6.5, 16.22, 6.5, 15.52)

# FILL TEMPLATE
box(6.5, 15.1, 4.5, 0.95,
    ['填充 task_generator_prompt.md',
     '<<JOB_TITLE>>  <<ROLE_TASKS>>',
     '<<SELECTED_TASK>>  <<TARGET_FORMAT>>  <<FORMAT_CONSTRAINTS>>'],
    C_PROC, B_PROC, fs=8.5, bold_first=True)

arrow(6.5, 14.62, 6.5, 13.92)

# API CALL
box(6.5, 13.5, 4.5, 0.95,
    ['OpenAI API  ·  model: gpt-5.1',
     '64 并发 workers  (ThreadPoolExecutor)',
     '每条独立重试 3 次，指数退避'],
    C_PROC, B_PROC, fs=8.5, bold_first=True)

arrow(6.5, 13.02, 6.5, 12.32)

# VALIDATE DIAMOND
diamond(6.5, 11.85, 3.4, 0.95,
        ['验证通过?', 'JSON 格式 / prompt>80词 / rubric≥10条'],
        C_DEC, B_DEC, fs=8.5)

# NO branch → skip
ax.annotate('', xy=(3.5, 11.85), xytext=(4.8, 11.85),
            arrowprops=dict(arrowstyle='->', color=ARROW_C, lw=1.5, mutation_scale=14),
            zorder=5)
box(2.7, 11.85, 1.5, 0.6, ['跳过\n(log 错误)'], '#FDEDEC', '#E74C3C', fs=8.5)
ax.text(4.15, 11.95, 'No', fontsize=8, color='#E74C3C', fontweight='bold')

# YES branch → write file
arrow(6.5, 11.37, 6.5, 10.67, label='Yes', label_dx=0.12)

# WRITE OUTPUT
box(6.5, 10.3, 4.5, 0.8,
    ['写入 generated_tasks.jsonl',
     '{ "prompt": "...",  "rubric": "..." }'],
    C_FILE, B_FILE, fs=8.8, bold_first=True)

arrow(6.5, 9.9, 6.5, 9.22)

# COUNT DIAMOND
diamond(6.5, 8.75, 3.0, 0.9,
        ['已满 5000 条?'],
        C_DEC, B_DEC, fs=9)

# loop back (No) — L-shaped path on left side
ax.plot([5.0, 1.8], [8.75, 8.75], color=ARROW_C, lw=1.5, zorder=5)
ax.plot([1.8,  1.8], [8.75, 16.7], color=ARROW_C, lw=1.5, zorder=5)
ax.plot([1.8,  4.25], [16.7, 16.7], color=ARROW_C, lw=1.5, zorder=5)
ax.annotate('', xy=(4.25, 16.7), xytext=(3.7, 16.7),
            arrowprops=dict(arrowstyle='->', color=ARROW_C,
                            lw=1.5, mutation_scale=14), zorder=5)
ax.text(1.1, 12.8, 'No\n继续生成', fontsize=8, color='#27AE60',
        fontweight='bold', ha='center')

# YES → next phase
arrow(6.5, 8.3, 6.5, 7.62, label='Yes  (5000 条完成)', label_dx=0.12)

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 BANNER
phase_banner(7.28, '② 任务执行阶段  Claude Code Agent  ×  5000', '#D5F5E3')

# SANDBOX
box(6.5, 6.5, 5.5, 1.05,
    ['隔离沙箱 (每条任务独立)',
     '读取 prompt  →  启动 Claude Code Agent',
     '可用工具: 浏览网页 / 创建文件 / 写代码 / 执行命令'],
    C_SAND, B_SAND, fs=8.8, bold_first=True)

arrow(6.5, 5.97, 6.5, 5.27)

# EXECUTE
box(6.5, 4.9, 5.5, 0.8,
    ['Agent 执行任务，产出 deliverable',
     'Word / PDF / Excel / PowerPoint / ZIP / code ...'],
    C_SAND, B_SAND, fs=8.8, bold_first=True)

arrow(6.5, 4.5, 6.5, 3.82)

# COLLECT
box(6.5, 3.45, 5.0, 0.8,
    ['收集完整执行轨迹 (trajectory)',
     '工具调用序列 + 中间状态 + 最终输出'],
    C_SAND, B_SAND, fs=8.8, bold_first=True)

arrow(6.5, 3.05, 6.5, 2.37)

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 BANNER
phase_banner(2.03, '③ 训练阶段', '#FADBD8')

# TRAIN
box(6.5, 1.3, 5.5, 0.95,
    ['5000 条 (task, trajectory) 对',
     '训练模型  →  提升 agentic task 完成能力',
     '对齐 train_filtered.jsonl 的任务分布'],
    C_TRAIN, B_TRAIN, fs=8.8, bold_first=True)

# ─────────────────────────────────────────────────────────────────────────────
# Title
ax.text(6.5, 19.82, 'Agentic Task 数据生成 Pipeline',
        ha='center', va='center', fontsize=13, fontweight='bold',
        color='#1A1A2E', zorder=6)

plt.tight_layout(pad=0.5)
plt.savefig('pipeline.png', dpi=150, bbox_inches='tight',
            facecolor='#FAFAFA')
print("Saved: pipeline.png")
