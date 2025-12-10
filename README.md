# Blender-Cross-Select
Select scene objects similar like RHINO or CAD（像RHINO/CAD那样选取元素）


Compared with Blender's native box selection tool, this plugin has been significantly optimized:
You can implement box selection logic that is the same as or similar to that in Rhino, CAD, and 3ds Max:
- When you drag to select from left to right, the **full match mode** will be activated. At this time, only objects whose vertices are completely within the square range will be selected.
- When you drag to select from right to left, the **partial match mode** will be activated. An object will be selected as long as any of its vertices falls within the square range.

Current supported features:
1. Supports cross-selection of vertices, edges, and faces in Edit Mode.
2. Supports cross-selection of meshes and other objects in Object Mode.
3. Adapts to two selection drawing modes: Box Selection and Lasso Selection.
4. Adapts to a wealth of shortcut keys to optimize operation experience; for details, please refer to the Preference Settings page of this plugin.

This plugin is highly optimized based on Blender's native selection function. With only a small amount of additional performance overhead, it achieves impressive selection capabilities.
