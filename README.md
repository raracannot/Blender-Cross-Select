# Blender-Cross-Select
Select scene objects similar like RHINO or CAD
像RHINO/CAD那样选取元素

Compared with Blender's native box selection tool, this plugin has been significantly optimized:
You can implement box selection logic that is the same as or similar to that in Rhino, CAD, and 3ds Max:
相比于blender原生的框选工具进行了大量的优化：
你可以实现类似rhino、cad、3dmax相同或相似的框选逻辑：

- When you drag to select from left to right, the **full match mode** will be activated. At this time, only objects whose vertices are completely within the square range will be selected.
- When you drag to select from right to left, the **partial match mode** will be activated. An object will be selected as long as any of its vertices falls within the square range.
当你从左向右框选时，将会执行完全匹配模式，此时，只有顶点完全处于方形范围的物体将被选中
当你从右向左框选时，将会执行半匹配模式，只要任意顶点处于方形范围内，物体即可被选中

Current supported features:
目前已经支持：
1. Supports cross-selection of vertices, edges, and faces in Edit Mode.
2. Supports cross-selection of meshes and other objects in Object Mode.
3. Adapts to two selection drawing modes: Box Selection and Lasso Selection.
4. Adapts to a wealth of shortcut keys to optimize operation experience; for details, please refer to the Preference Settings page of this plugin.
1.支持在网格编辑模式对点线面进行交叉选取
2.支持在物体模式下对网格及其他对象进行交叉选取
3.已经适配框选选取和套索选取两种选区绘制模式
4.已经适配丰富的快捷键可优化操作手感，具体见本插件的偏好设置说明页

This plugin is highly optimized based on Blender's native selection function. With only a small amount of additional performance overhead, it achieves impressive selection capabilities.
本插件在原生选取功能的基础上进行高度优化，在仅增加部分有限性能开销前提下，实现了令人惊喜的选取能力
