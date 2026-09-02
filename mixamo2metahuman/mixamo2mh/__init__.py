"""Mixamo -> UE5 / MetaHuman: conversie de personaje si animatii.

Fluxul: FBX de la Mixamo -> Blender (redenumire oase in conventia UE5, os
`root`, root motion, export FBX) -> import in Unreal Engine 5 -> retarget pe
MetaHuman prin IK Retargeter.
"""

__version__ = "1.0.0"
__all__ = ["settings", "bone_map", "blender", "unreal_script", "cli"]
