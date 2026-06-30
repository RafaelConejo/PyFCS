import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch

# -----------------------------
# Configuration
# -----------------------------
output_path = "fuzzy_purple_yellow_membership_pretty.png"

# Position of the sample in the gradient
# 0 = Purple, 1 = Yellow
sample_pos = 0.43

# Membership degrees (illustrative)
mu_purple = 1 - sample_pos
mu_yellow = sample_pos

# Main colors
purple = "#6A0DAD"
yellow = "#F4D03F"
sample_color = "#A97BC7"

# -----------------------------
# Figure
# -----------------------------
fig, ax = plt.subplots(figsize=(14, 5))
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

# -----------------------------
# Gradient bar
# -----------------------------
gradient = np.linspace(0, 1, 1200).reshape(1, -1)
cmap = LinearSegmentedColormap.from_list("purple_yellow", [purple, yellow])

bar_y0 = 0.48
bar_y1 = 0.63

ax.imshow(
    gradient,
    aspect="auto",
    cmap=cmap,
    extent=[0, 1, bar_y0, bar_y1],
    zorder=1
)

# Rounded border effect with fancy box
box = FancyBboxPatch(
    (0, bar_y0), 1, bar_y1 - bar_y0,
    boxstyle="round,pad=0.015,rounding_size=0.04",
    linewidth=1.6,
    edgecolor="black",
    facecolor="none",
    zorder=3
)
ax.add_patch(box)

# Endpoint labels
ax.text(
    0.00, 0.74, "Purple",
    ha="center", va="bottom",
    fontsize=20, fontweight="bold", color=purple
)

ax.text(
    1.00, 0.74, "Yellow",
    ha="center", va="bottom",
    fontsize=20, fontweight="bold", color="#B7950B"
)

# Endpoint dots
ax.scatter(0, (bar_y0 + bar_y1)/2, s=220, color=purple, edgecolor="black", zorder=5)
ax.scatter(1, (bar_y0 + bar_y1)/2, s=220, color=yellow, edgecolor="black", zorder=5)

# -----------------------------
# Sample point
# -----------------------------
sample_y = (bar_y0 + bar_y1)/2

# Shadow
ax.scatter(
    sample_pos + 0.005, sample_y - 0.008,
    s=340, color="0.75", alpha=0.35, edgecolor="none", zorder=5
)

# Main sample point
ax.scatter(
    sample_pos, sample_y,
    s=320, color=sample_color,
    edgecolor="black", linewidth=1.6, zorder=6
)

# Vertical guide
ax.plot(
    [sample_pos, sample_pos],
    [0.20, 0.82],
    linestyle="--",
    linewidth=1.3,
    color="0.25",
    zorder=2
)

# -----------------------------
# Title
# -----------------------------
ax.text(
    0.5, 0.93,
    "Fuzzy membership between color categories",
    ha="center", va="center",
    fontsize=22, fontweight="bold"
)

# Subtitle
ax.text(
    0.5, 0.87,
    "A color sample can partially belong to more than one category",
    ha="center", va="center",
    fontsize=13, color="0.35"
)

# -----------------------------
# Membership boxes
# -----------------------------
left_text = f"Membership to Purple\nμ = {mu_purple:.2f}"
right_text = f"Membership to Yellow\nμ = {mu_yellow:.2f}"

ax.text(
    0.20, 0.14, left_text,
    ha="center", va="center",
    fontsize=14,
    bbox=dict(
        boxstyle="round,pad=0.5",
        facecolor="#F4ECFB",
        edgecolor=purple,
        linewidth=1.4
    )
)

ax.text(
    0.80, 0.14, right_text,
    ha="center", va="center",
    fontsize=14,
    bbox=dict(
        boxstyle="round,pad=0.5",
        facecolor="#FEF9E7",
        edgecolor="#B7950B",
        linewidth=1.4
    )
)

# Arrows to membership boxes
ax.annotate(
    "",
    xy=(sample_pos, 0.24),
    xytext=(0.20, 0.19),
    arrowprops=dict(arrowstyle="->", lw=1.4, color=purple)
)

ax.annotate(
    "",
    xy=(sample_pos, 0.24),
    xytext=(0.80, 0.19),
    arrowprops=dict(arrowstyle="->", lw=1.4, color="#B7950B")
)

# -----------------------------
# Sample label
# -----------------------------
ax.text(
    sample_pos, 0.30,
    "Sample color",
    ha="center", va="center",
    fontsize=14, fontweight="bold",
    bbox=dict(
        boxstyle="round,pad=0.35",
        facecolor="white",
        edgecolor="0.3",
        linewidth=1.1
    )
)

# -----------------------------
# Clean layout
# -----------------------------
ax.set_xlim(-0.07, 1.07)
ax.set_ylim(0, 1)
ax.axis("off")

plt.tight_layout()
plt.savefig(output_path, dpi=300, bbox_inches="tight")
plt.show()

print(f"Saved figure as: {output_path}")