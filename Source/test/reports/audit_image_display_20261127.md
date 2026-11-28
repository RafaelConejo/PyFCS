# Image Display controller extraction audit

Baseline: Source(20261127-161835).zip plus PyFCS_Model3DManager_Refactor.zip.

- Regression suite: 57 tests, 56 passed, 1 skipped (missing dental model), zero failures and errors.
- Optional GUI checks: creation, Model 3D, Image Display passed under Linux/Xvfb.
- Before/after comparison: 32 recorded outputs equal, including image array SHA-256 digests, viewport dictionaries and pixel/ROI sampling.
- Scientific core, VisualManager, Model3DManager, ColorProcessingEngine, ImageWorkspaceManager and ImageInspectionManager unchanged byte for byte.
- Windows/PyInstaller and historical interactive scripts not exercised.

## Compared records

```json
{
  "grid_original": [
    [
      244,
      367,
      4
    ],
    "uint8",
    "0dca4602a54193ed82532506404e6deddd8beebbe7be43d16098b3513ab1093b"
  ],
  "grid_original_view": {
    "zoom": 1.0,
    "cx": 45.0,
    "cy": 30.0
  },
  "zoom": [
    [
      244,
      367,
      4
    ],
    "uint8",
    "75b3497753f723c7d271ed0459737594d6a172e1f995b31c56dcb26e610aa332"
  ],
  "zoom_view": {
    "zoom": 1.15,
    "cx": 44.98400663428504,
    "cy": 30.0
  },
  "pan": [
    [
      244,
      367,
      4
    ],
    "uint8",
    "4d55c58a5a86a9792a60d12411baa2d6eb99c5030453d44f80cb1e2dd51cdd41"
  ],
  "pan_view": {
    "zoom": 1.15,
    "cx": 42.851557872290016,
    "cy": 28.5032074126871
  },
  "pixel": [
    27,
    18,
    [
      35.4412680307649,
      1.24008712424864,
      12.834848784329678
    ]
  ],
  "roi": {
    "type": "roi",
    "x1": 27,
    "y1": 18,
    "x2": 58,
    "y2": 38,
    "width": 32,
    "height": 21,
    "pixels": 672,
    "center_x": 43,
    "center_y": 28,
    "mean_rgb": [
      141,
      123,
      98
    ]
  },
  "roi_lab": [
    52.600676451410564,
    3.1793375032998266,
    16.029980016606196
  ],
  "focus": [
    [
      334,
      501,
      4
    ],
    "uint8",
    "d6fd3744070d7b528d7681829561e4d1be804cef8e3fe2e5cd219341a62a1111"
  ],
  "focus_view": {
    "zoom": 1.15,
    "cx": 42.851557872290016,
    "cy": 28.5032074126871
  },
  "resized": [
    [
      264,
      396,
      4
    ],
    "uint8",
    "adba44a8d6d881e7791cf318f9627d4e4d8c9d0e5909e91809cbe965e7c463d7"
  ],
  "resized_view": {
    "zoom": 1.0,
    "cx": 45.0,
    "cy": 30.0
  },
  "single_membership": [
    [
      264,
      396
    ],
    "uint8",
    "fae5c8570dec8b3b18c89dbc881e9244e25d5e07227ebf47eb184ca36a10dd20"
  ],
  "single": [
    [
      264,
      396,
      4
    ],
    "uint8",
    "d8e88ee5de0cc95b307c355b2aa51ad9da456f736ab9f7e948456728a7df6a8d"
  ],
  "single_view": {
    "zoom": 1.0,
    "cx": 198.0,
    "cy": 132.0
  },
  "single_color": [
    [
      264,
      396,
      4
    ],
    "uint8",
    "adba44a8d6d881e7791cf318f9627d4e4d8c9d0e5909e91809cbe965e7c463d7"
  ],
  "single_color_view": {
    "zoom": 1.0,
    "cx": 198.0,
    "cy": 132.0
  },
  "general_labels": [
    [
      264,
      396
    ],
    "int32",
    "673da2701dd74c13b8fd90f405409ee5d200767035cb4ab557f47548385881f9"
  ],
  "detailed_labels": [
    [
      264,
      396
    ],
    "int32",
    "03eda2ddc10a4b62f6346b551676165338f1eef166d2704e3c62f3690fa4a76c"
  ],
  "all_general": [
    [
      264,
      396,
      4
    ],
    "uint8",
    "037841c585ad7a28930ca88a920fdbec4715954bf2af2e2827c3c5c5aab5b7a8"
  ],
  "all_general_view": {
    "zoom": 1.0,
    "cx": 198.0,
    "cy": 132.0
  },
  "all_detailed": [
    [
      264,
      396,
      4
    ],
    "uint8",
    "17c7fba5e4d0b1eb6efd7a3590d8ace850c8654bbf81d6cec158b014016d512c"
  ],
  "all_detailed_view": {
    "zoom": 1.0,
    "cx": 198.0,
    "cy": 132.0
  },
  "all_alt": [
    [
      264,
      396,
      4
    ],
    "uint8",
    "77447b5ec6f9d766434897b589d00dbfb395e4b4c87430e14fd6a7ac08400cdf"
  ],
  "all_alt_view": {
    "zoom": 1.0,
    "cx": 198.0,
    "cy": 132.0
  },
  "all_max": [
    [
      264,
      396,
      4
    ],
    "uint8",
    "77447b5ec6f9d766434897b589d00dbfb395e4b4c87430e14fd6a7ac08400cdf"
  ],
  "all_max_view": {
    "zoom": 1.0,
    "cx": 198.0,
    "cy": 132.0
  },
  "export": [
    [
      264,
      396,
      4
    ],
    "uint8",
    "77447b5ec6f9d766434897b589d00dbfb395e4b4c87430e14fd6a7ac08400cdf"
  ],
  "legend": [
    [
      150,
      114,
      3
    ],
    "uint8",
    "9ab761d806bff385e8505c2ce23df25cef25a0887dae94abdeae5cd09f6adf55"
  ],
  "restored": [
    [
      264,
      396,
      4
    ],
    "uint8",
    "adba44a8d6d881e7791cf318f9627d4e4d8c9d0e5909e91809cbe965e7c463d7"
  ],
  "restored_view": {
    "zoom": 1.0,
    "cx": 45.0,
    "cy": 30.0
  }
}
```
