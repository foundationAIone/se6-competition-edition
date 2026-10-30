# Dependency and asset review

The runtime recipe pins versions, not platform-specific wheel hashes. A Linux image
build, resolved wheel hashes and base-image digest remain clean-build acceptance work.
Installed license files were inspected in the QA interpreter; that observation does
not grant ownership of application or inherited native source.

| Runtime dependency | Version | License observed |
|---|---|---|
| pydantic | 2.12.4 | MIT |
| pydantic-core | 2.41.5 | MIT |
| annotated-types | 0.7.0 | MIT |
| typing-extensions | 4.15.0 | PSF-2.0; complete composite notice |
| typing-inspection | 0.4.2 | MIT |

Test dependencies: pytest 8.4.2, iniconfig 2.3.0 and pluggy 1.6.0 use MIT;
packaging 25.0 declares Apache-2.0 OR BSD-2-Clause; Pygments 2.19.2 uses BSD-2-Clause;
Windows-only colorama 0.4.6 uses BSD-3-Clause. Their full installed notices must be
retained. This package references dependencies rather than bundling their distributions.

The hosted frontend uses local HTML, CSS and JavaScript with system font fallbacks.
No downloaded fonts, third-party images or model weights are included. New screenshots
must be reviewed for privacy and display rights before public recording or upload.

The official NVIDIA Nemotron-3-Super model card declares the NVIDIA Nemotron Open
Model License. The historical provider identifier names that model family; its exact
weight commit and quantization are not established by the capture. Full model and
provider terms still require owner review. Do not apply the proposed project MIT
license to NVIDIA weights or assume a license for provider outputs.

[Official NVIDIA model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16)
