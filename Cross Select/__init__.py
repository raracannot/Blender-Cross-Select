
#交错选择器，在物体及编辑模式下，像RHINO或CAD那样，根据鼠标不同的运动方式进行更加智能的场景对象选择

bl_info = {
    "name": "Cross Select",
    "author": "RARA, CYX, Witty.Ming, Shuimeng",
    "version": (1, 0, 2),
    "blender": (3, 6, 0),
    "location": "View3D > Toolbar (T-Panel)",
    "description": "Select scene objects similar like RHINO or CAD（像RHINO/CAD那样选取元素）.",
    "category": "3D View",
}

import os
import bpy
import gpu
import time
import bmesh
import numpy as np

from gpu_extras.batch import batch_for_shader
from mathutils import Vector,Matrix
from bpy_extras import view3d_utils
from . import translation

# ============================== 数学辅助函数 ==============================
def compute_polygon_area(pts):
    area = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += (x1 * y2 - x2 * y1)
    return area * 0.5

def ccw(A, B, C):
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

def intersect(A, B, C, D):
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

def is_segment_intersecting_rect(p1, p2, rect):
    min_x, min_y = rect[0]
    max_x, max_y = rect[1]
    if max(p1.x, p2.x) < min_x or min(p1.x, p2.x) > max_x or \
            max(p1.y, p2.y) < min_y or min(p1.y, p2.y) > max_y:
        return False
    r1 = (min_x, min_y);
    r2 = (max_x, min_y)
    r3 = (max_x, max_y);
    r4 = (min_x, max_y)
    line_start = (p1.x, p1.y);
    line_end = (p2.x, p2.y)
    if intersect(line_start, line_end, r1, r2): return True
    if intersect(line_start, line_end, r2, r3): return True
    if intersect(line_start, line_end, r3, r4): return True
    if intersect(line_start, line_end, r4, r1): return True
    return False

def is_segment_intersecting_poly(p1, p2, poly):
    line_start = (p1.x, p1.y);
    line_end = (p2.x, p2.y)
    n = len(poly)
    for i in range(n):
        p3 = poly[i];
        p4 = poly[(i + 1) % n]
        if intersect(line_start, line_end, p3, p4): return True
    return False

def is_object_in_rect(obj, context, rect, select_mode):
    coords = get_sampled_coords(obj, context)
    if not coords:
        return False
    if select_mode == 'FULLY':
        for co in coords:
            if not is_point_in_rect((co.x, co.y), rect):
                return False
        return True
    else:
        for co in coords:
            if is_point_in_rect((co.x, co.y), rect):
                return True
        return False

def is_object_in_lasso(obj, context, poly, select_mode):
    coords = get_sampled_coords(obj, context)
    if not coords:
        return False
    if select_mode == 'FULLY':
        for co in coords:
            if not is_point_in_polygon((co.x, co.y), poly):
                return False
        return True
    else:
        for co in coords:
            if is_point_in_polygon((co.x, co.y), poly):
                return True
        return False

def get_sampled_coords(obj, context, use_smart_sampling=True):
    #一般情况下，物体模式使用use_smart_sampling=True加速，编辑模式不得加速，需完整遍历
    if obj.type == 'MESH' and obj.data.vertices:
        verts = obj.data.vertices
        return make_3d_to_region_2d(verts, obj.matrix_world, context.region, context.region_data, use_smart_sampling)
    else:
        co = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, obj.matrix_world @ Vector((0, 0, 0)))
        return [co] if co else []

def is_point_in_rect(point, rect):
    x, y = point
    return (rect[0][0] <= x <= rect[1][0] and rect[0][1] <= y <= rect[1][1])

def is_point_in_polygon(point, poly):
    x, y = point
    inside = False
    n = len(poly)
    px1, py1 = poly[0]
    for i in range(1, n + 1):
        px2, py2 = poly[i % n]
        if y > min(py1, py2):
            if y <= max(py1, py2):
                if x <= max(px1, px2):
                    if py1 != py2:
                        xinters = (y - py1) * (px2 - px1) / (py2 - py1 + 1e-8) + px1
                    if px1 == px2 or x <= xinters:
                        inside = not inside
        px1, py1 = px2, py2
    return inside

def make_3d_to_region_2d(verts, matrix_world, region, region_data, use_smart_sampling=True):
    # 将一组 3D 顶点批量转换为 2D 屏幕坐标。
    # 参数:
    # - verts: 3D 顶点列表 (obj.data.vertices)
    # - matrix_world: 对象的世界矩阵 (obj.matrix_world)
    # - region: 视图区域 (context.region)
    # - region_data: 视图参数 (region_data)
    # - use_smart_sampling: 是否使用智能采样 (默认: True)
    # 返回:
    # - 2D 屏幕坐标列表 (mathutils.Vector)

    vlen = len(verts)
    perspective_matrix = region_data.perspective_matrix
    # 将顶点坐标转换为 NumPy 数组
    if use_smart_sampling:
        step = max(1, 1 + ((vlen - 1) // 1000) * 10)
        coords_3d = np.array([verts[i].co.to_tuple() for i in range(0, vlen, step)])
    else:
        coords_3d = np.array([v.co.to_tuple() for v in verts])
    coords_3d = np.hstack((coords_3d, np.ones((coords_3d.shape[0], 1))))  # 添加第四列（齐次坐标）
    # 应用世界矩阵
    coords_3d = np.dot(coords_3d, np.array(matrix_world.transposed()))
    # 应用视图矩阵和投影矩阵
    coords_2d = np.dot(coords_3d, np.array(perspective_matrix.transposed()))
    # 进行透视除法
    coords_2d /= coords_2d[:, 3].reshape(-1, 1)
    # 转换为屏幕坐标
    coords_2d[:, 0] = (coords_2d[:, 0] + 1) * 0.5 * region.width
    coords_2d[:, 1] = (coords_2d[:, 1] + 1) * 0.5 * region.height
    # 过滤掉在视图外的点，但一般不需要，暂时注释掉
    # coords_2d = coords_2d[(coords_2d[:, 0] >= 0) & (coords_2d[:, 0] <= width) & (coords_2d[:, 1] >= 0) & (coords_2d[:, 1] <= height)]
    # 返回 2D 屏幕坐标列表
    return [Vector((co[0], co[1])) for co in coords_2d]

# ============================== 绘制回调 ==============================
def draw_callback_px(self, context):
    prefs = bpy.context.preferences.addons[__package__].preferences
    if not self.is_dragging:
        return

    # 兼容 Blender 4.0+ 的 Shader 获取方式
    try:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    except Exception:
        # 尝试 4.0+ 新名称
        try:
            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        except:
            shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')

    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(prefs.line_width)

    draw_mode = prefs.select_draw_mode
    cross_line_color = (prefs.cross_line_color[0],prefs.cross_line_color[1],prefs.cross_line_color[2],1)
    contain_line_color = (prefs.contain_line_color[0],prefs.contain_line_color[1],prefs.contain_line_color[2],1)

    color = contain_line_color if self.select_mode == 'FULLY' else cross_line_color
    line_style = 'SOLID' if self.select_mode == 'FULLY' else 'DASHED'

    if draw_mode == 'BOX':
        min_x , max_x, min_y, max_y = self.box_path
        vertices = (
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
            (min_x, min_y))

        shader.bind()
        shader.uniform_float("color", color)
        draw_select_line(shader, vertices, line_style)
    else:
        if len(self.lasso_path) > 1:
            shader.bind()
            shader.uniform_float("color", color)
            path = self.lasso_path + [self.lasso_path[0]]
            draw_select_line(shader, path, line_style)

    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')

def draw_select_line(shader, vertices, line_style):
    if line_style == 'SOLID':
        border_batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": vertices})
        border_batch.draw(shader)
    else:
        dash_length = 10
        gap_length = 5
        dash_vertices = []
        for i in range(len(vertices) - 1):
            start = Vector(vertices[i])
            end = Vector(vertices[i + 1])
            line_dir = (end - start).normalized()
            line_length = (end - start).length
            num_dashes = int(line_length // (dash_length + gap_length))
            for j in range(num_dashes):
                dash_start = start + line_dir * (j * (dash_length + gap_length))
                dash_end = dash_start + line_dir * dash_length
                if (dash_end - start).length > line_length:
                    dash_end = end
                dash_vertices.extend([dash_start, dash_end])
            remaining_length = line_length - num_dashes * (dash_length + gap_length)
            if remaining_length > 0:
                dash_start = start + line_dir * (num_dashes * (dash_length + gap_length))
                dash_end = dash_start + line_dir * min(dash_length, remaining_length)
                dash_vertices.extend([dash_start, dash_end])
        if dash_vertices:
            border_batch = batch_for_shader(shader, 'LINES', {"pos": dash_vertices})
            border_batch.draw(shader)

# ============================== 操作符 (Operator) ==============================
class RARA_OT_ULTIMATE_Public_SelectTools(bpy.types.Operator):
    bl_idname = "rara.view3d_ultimate_public_select_tool"
    bl_label = "Ultimate Cross Select" #全模式交错选择
    bl_options = {'REGISTER', 'BLOCKING', 'UNDO'}
    bl_description = "Cross Selector, intelligently select scene objects based on different mouse movements\n\n【Blue】: Fully Match, select object only when all vertices are within the range\n【Orange】: Half Match, select object when some vertices are within the selection range\n\n【shift】: Add Selection\n【ctrl】: Subtract Selection"
    #交错选择器，根据鼠标不同的运动，更加智能的选择场景对象\n\n【蓝色】：完全匹配，当所有顶点都在范围内时，才选中对象\n【橙色】：半匹配，当部分顶点在选择范围内时，即选中对象\n\n【shift】：加选\n【ctrl】：减选

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)# blender4.5 兼容
        self.draw_handle = None
        self.start_mouse = (0, 0)
        self.end_mouse = (0, 0)
        self.draw_mode = 'BOX'
        self.select_mode = 'FULLY'
        self.operation = 'SET'
        self.is_dragging = False
        self.drag_threshold = 5

        self.box_path = [] #[xmin, xmax, ymin, ymax]
        self.lasso_path = []

    def invoke(self, context, event):
        #初始化，记录鼠标起始位置（区域内坐标）
        prefs = bpy.context.preferences.addons[__package__].preferences
        self.draw_mode = prefs.select_draw_mode
        self.start_mouse = (event.mouse_region_x, event.mouse_region_y)
        self.end_mouse = self.start_mouse  # 初始化结束位置为起始位置
        self.is_dragging = False  # 标记当前未开始拖拽
        self.lasso_path = [self.start_mouse]  # 初始化圈选路径，起点为鼠标起始位置
        #执行handler
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        prefs = bpy.context.preferences.addons[__package__].preferences

        if event.shift: #shift：加选
            self.operation = 'ADD'
        elif event.ctrl: #ctrl：减选
            self.operation = 'SUB'
        else: #普通：替选
            self.operation = 'SET'

        if event.type == 'MOUSEMOVE':
            if not self.is_dragging:
                delta = Vector((event.mouse_region_x, event.mouse_region_y)) - Vector(self.start_mouse)
                if delta.length > self.drag_threshold:
                    self.start_dragging(context)
            if self.is_dragging:
                if self.draw_mode == 'BOX':
                    self.update_drag_position(event)
                else:
                    self.update_lasso_path(event)
                context.area.tag_redraw()

        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            start_time = time.time()
            if self.is_dragging:
                if self.draw_mode == 'BOX':
                    self.finish_box_select(context)
                else:
                    self.finish_lasso_select(context)
            else:
                self.handle_single_click(context, event)

            if prefs.show_debug:
                end_time = time.time()
                self.report({'INFO'}, f"选择操作耗时: {end_time - start_time:.4f}秒")
            return {'FINISHED'}

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cancel_operation(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def start_dragging(self, context):
        self.is_dragging = True
        self.draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback_px, (self, context), 'WINDOW', 'POST_PIXEL')
        context.area.tag_redraw()

    def update_drag_position(self, event):
        self.end_mouse = (event.mouse_region_x, event.mouse_region_y)
        self.select_mode = 'FULLY' if self.end_mouse[0] > self.start_mouse[0] else 'HALF'
        x1, y1 = self.start_mouse
        x2, y2 = self.end_mouse
        self.box_path = (min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2))

    def update_lasso_path(self, event):
        area = compute_polygon_area(self.lasso_path)
        self.select_mode = 'FULLY' if area >= 0 else 'HALF'
        mouse_pos = (event.mouse_region_x, event.mouse_region_y)
        if (not self.lasso_path) or (Vector(mouse_pos) - Vector(self.lasso_path[-1])).length > 2:
            self.lasso_path.append(mouse_pos)

    def finish_box_select(self, context):
        self.cleanup_drawing()
        self.lasso_path = self.box_path
        if context.mode == 'OBJECT':
            self.process_selection_object(context)
        elif context.mode == 'EDIT_MESH':
            self.process_selection_edit(context)
        context.area.tag_redraw()

    def finish_lasso_select(self, context):
        self.cleanup_drawing()

        min_x = min(p[0] for p in self.lasso_path)
        max_x = max(p[0] for p in self.lasso_path)
        min_y = min(p[1] for p in self.lasso_path)
        max_y = max(p[1] for p in self.lasso_path)
        #xmin, xmax, ymin, ymax
        self.box_path = (min_x , max_x, min_y, max_y)

        if context.mode == 'OBJECT':
            self.process_selection_object(context)
        elif context.mode == 'EDIT_MESH':
            self.process_selection_edit(context)
        context.area.tag_redraw()

    # --- 物体模式的逻辑 ---
    def process_selection_object(self, context):

        # 保存当前选择
        original_selection = set(context.selected_objects)

        # 清空选择，使用 'ADD' 模式捕获框内物体
        bpy.ops.object.select_all(action='DESELECT')

        min_x , max_x, min_y, max_y = self.box_path
        bpy.ops.view3d.select_box(wait_for_input=False, xmin=min_x, xmax=max_x, ymin=min_y, ymax=max_y, mode='ADD')

        # 得到所有碰到的物体
        touched_objects = set(context.selected_objects)

        # 恢复原始选择，进入 Python 逻辑计算
        bpy.ops.object.select_all(action='DESELECT')
        for obj in original_selection:
            obj.select_set(True)

        # 筛选出符合 "Contain/Cross" 逻辑的物体
        valid_selection = set()

        for obj in touched_objects:
            is_valid = False #默认无效
            # 如果是 HALF，只要碰到了(touched)就算选中
            if self.select_mode == 'HALF':
                is_valid = True
            # 如果是 FULLY，必须完全在内
            else:
                if self.draw_mode == 'BOX':
                    min_x , max_x, min_y, max_y = self.box_path
                    is_valid = is_object_in_rect(obj, context, ((min_x, min_y), (max_x, max_y)), self.select_mode)
                else:
                    is_valid = is_object_in_lasso(obj, context, self.lasso_path, self.select_mode)

            if is_valid:
                valid_selection.add(obj)

        # 执行集合运算
        final_selected = set()
        if self.operation == 'SET':
            final_selected = valid_selection
        elif self.operation == 'ADD':
            final_selected = original_selection.union(valid_selection)
        elif self.operation == 'SUB':
            final_selected = original_selection - valid_selection

        # 应用结果
        bpy.ops.object.select_all(action='DESELECT')

        for obj in final_selected:
            obj.select_set(True)

        if context.view_layer.objects.active in final_selected:
            context.view_layer.objects.active = context.view_layer.objects.active

    # --- 编辑模式的逻辑 ---
    def process_selection_edit(self, context):#process_box_selection_edit & process_lasso_selection_edit
        if hasattr(context, "objects_in_mode_unique_data"):
            edit_objs = [obj for obj in context.objects_in_mode_unique_data if obj.type == 'MESH']
        elif hasattr(context, "objects_in_mode"):
            edit_objs = [obj for obj in context.objects_in_mode if obj.type == 'MESH']
        else:
            obj = context.edit_object
            edit_objs = [obj] if obj and obj.type == 'MESH' else []
        if not edit_objs:
            return

        # 获取当前编辑模式（顶点/边/面）
        mesh_select_mode = context.tool_settings.mesh_select_mode
        is_vert, is_edge, is_face = mesh_select_mode

        # 点模式下，直接使用默认框选器，无需额外处理
        if is_vert:
            if self.draw_mode == 'BOX':
                min_x , max_x, min_y, max_y = self.box_path
                bpy.ops.view3d.select_box(wait_for_input=False, xmin=min_x, xmax=max_x, ymin=min_y, ymax=max_y, mode=self.operation)
            else:
                #官方物体模式的路径选择，只能选择原点
                base_time = time.time()
                path = [{
                    "name": f"point_{i}",
                    "loc": (p[0], p[1]),
                    "time": base_time + i * 0.001
                    } for i, p in enumerate(self.lasso_path)]
                bpy.ops.view3d.select_lasso('EXEC_DEFAULT', path=path, mode=self.operation)
            # for obj in edit_objs:
                # bmesh.update_edit_mesh(obj.data)
            return

        # 面且框且半选模式下，直接使用默认框选器，无需额外处理
        elif is_face and self.draw_mode == 'BOX' and self.select_mode == 'HALF':
            min_x , max_x, min_y, max_y = self.box_path
            bpy.ops.view3d.select_box(wait_for_input=False, xmin=min_x, xmax=max_x, ymin=min_y, ymax=max_y, mode=self.operation)
            return

        bm_cache = {}
        original = {}
        element_key = 'edges' if is_edge else 'faces'

        for obj in edit_objs:
            # 初始化BMesh并保存初始选择（初始网格）
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            bm_cache[obj] = bm

            #记录初始的选集
            elems = bm.edges if is_edge else bm.faces
            original[obj] = {ele for ele in elems if ele.select}

        # 清空选择，执行原生框选获取可触网格
        bpy.ops.mesh.select_all(action='DESELECT')

        #切换到面选择模式，再切换到边选择，这样有利于后续处理
        if self.draw_mode == 'BOX':
            min_x , max_x, min_y, max_y = self.box_path
            for temp_select_mode in ((False, False, True), (False, True, False)):
                bpy.context.tool_settings.mesh_select_mode = temp_select_mode
                bpy.ops.view3d.select_box(wait_for_input=False, xmin=min_x, xmax=max_x, ymin=min_y, ymax=max_y, mode='ADD')
        else:
            #官方物体模式的路径选择，只能选择原点
            base_time = time.time()
            path = [{
                "name": f"point_{i}",
                "loc": (p[0], p[1]),
                "time": base_time + i * 0.001
                } for i, p in enumerate(self.lasso_path)]
            for temp_select_mode in ((False, False, True), (False, True, False)):
                bpy.context.tool_settings.mesh_select_mode = temp_select_mode
                bpy.ops.view3d.select_lasso('EXEC_DEFAULT',path=path,mode='ADD')
        # 还原选择模式
        bpy.context.tool_settings.mesh_select_mode = (is_vert, is_edge, is_face)

        # 准备选区数据（适配不同绘制模式）
        if self.draw_mode == 'BOX':
            rect_poly = ((min_x, min_y), (max_x, max_y))  # 矩形格式
        else:
            rect_poly = self.lasso_path  # 多边形路径

        valid = {}
        for obj, bm in bm_cache.items():
            elems = bm.edges if is_edge else bm.faces
            # 获取可触网格（原生框选选中的元素）
            touched = {ele for ele in elems if ele.select}
            # 按当前选择模式筛选符合「完全匹配/半匹配」的有效元素
            valid[obj] = {ele for ele in touched if self.is_element_valid(context, obj, rect_poly, ele, element_key)}

        final = {}
        # 执行集合运算（SET/ADD/SUB）
        for obj in edit_objs:
            if self.operation == 'SET':
                # 设选：最终 = 有效网格
                final[obj] = valid[obj]
            elif self.operation == 'ADD':
                final[obj] = original[obj] | valid[obj]
            else:  # SUB
                # 减选：最终 = 初始 - 有效
                final[obj] = original[obj] - valid[obj]

        # 清空所有元素选择
        bpy.ops.mesh.select_all(action='DESELECT')

        if is_edge:#在for外先判断好，避免在for内判断，浪费性能
            for obj, bm in bm_cache.items():
                for e in final[obj]:
                    e.select = True

                    # 根据边检查相邻面
                    for f in e.link_faces:
                        if f.select: #如果已经被选中，不进行后续判断
                            continue
                        #遍历临面的边，如果边都在final[obj]里，将其选中
                        if all(edge in final[obj] for edge in f.edges):
                            f.select = True
                # bmesh.update_edit_mesh(obj.data)

        else:
            for obj, bm in bm_cache.items():
                for f in final[obj]:
                    f.select = True
                # bmesh.update_edit_mesh(obj.data)

    # 定义元素有效性判断函数
    def is_element_valid(self, context, obj, rect_poly, ele, ele_type):
        region = context.region
        rv3d = context.region_data
        matrix = obj.matrix_world
        # 判断单个元素（边/面）是否符合选择逻辑
        # 边模式
        if ele_type == 'edges':
            verts = ele.verts
            vert_2d = []
            all_inside = True
            any_inside = False
            for v in verts:
                co_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ v.co)
                if not co_2d:
                    all_inside = False
                    continue
                vert_2d.append(co_2d)
                if self.draw_mode == 'BOX':
                    is_in = is_point_in_rect((co_2d.x, co_2d.y), rect_poly)
                else:
                    is_in = is_point_in_polygon((co_2d.x, co_2d.y), rect_poly)
                if is_in:
                    any_inside = True
                else:
                    all_inside = False

            # 完全匹配：所有顶点在内；半匹配：任意顶点在内 或 边与选区相交
            if self.select_mode == 'FULLY':
                return all_inside
            else:
                if any_inside:
                    return True
                # 检测边与选区边界相交
                if len(vert_2d) == 2:
                    if self.draw_mode == 'BOX':
                        return is_segment_intersecting_rect(vert_2d[0], vert_2d[1], rect_poly)
                    else:
                        # 圈选模式下检测边与多边形相交
                        return is_segment_intersecting_poly(vert_2d[0], vert_2d[1], rect_poly)
                return False

        # 面模式
        elif ele_type == 'faces':
            verts = ele.verts
            vert_2d = []
            all_inside = True
            any_inside = False
            for v in verts:
                co_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ v.co)
                if not co_2d:
                    all_inside = False
                    continue
                vert_2d.append(co_2d)
                if self.draw_mode == 'BOX':
                    is_in = is_point_in_rect((co_2d.x, co_2d.y), rect_poly)
                else:
                    is_in = is_point_in_polygon((co_2d.x, co_2d.y), rect_poly)
                if is_in:
                    any_inside = True
                else:
                    all_inside = False

            # 完全匹配：所有顶点在内；半匹配：任意顶点在内 或 面的边与选区相交
            if self.select_mode == 'FULLY':
                return all_inside
            else:
                if any_inside:
                    return True
                # 检测面的边与选区边界相交
                is_crossing = False
                for i in range(len(vert_2d)):
                    p1 = vert_2d[i]
                    p2 = vert_2d[(i+1) % len(vert_2d)]
                    if p1 and p2:
                        if self.draw_mode == 'BOX':
                            if is_segment_intersecting_rect(p1, p2, rect_poly):
                                is_crossing = True
                                break
                        else:
                            if is_segment_intersecting_poly(p1, p2, rect_poly):
                                is_crossing = True
                                break
                return is_crossing
        return False

    def handle_single_click(self, context, event):
        # 单击选择处理，记录点选前选中集合，
        # 点选后如果选中集合未变化且无Shift/Ctrl修饰，认为点击空白区域，取消所有选择。
        if context.mode == 'OBJECT':
            before_selection = {obj.name for obj in context.selected_objects}
        elif context.mode == 'EDIT_MESH':
            obj = context.edit_object
            if obj and obj.type == 'MESH':
                before_selection = self.get_selected_mesh_elements(obj)
            else:
                before_selection = (set(), set(), set())
        else:
            before_selection = None

        try:
            # 调用Blender原生点选操作
            bpy.ops.view3d.select(
                'INVOKE_DEFAULT',
                extend=event.shift,
                deselect=event.ctrl,
                toggle=False,
                location=(event.mouse_region_x, event.mouse_region_y)
            )

        except Exception:
            pass

        if event.shift or event.ctrl:
            return

        if context.mode == 'OBJECT':
            after_selection = {obj.name for obj in context.selected_objects}
            if after_selection == before_selection:
                bpy.ops.object.select_all(action='DESELECT')

        elif context.mode == 'EDIT_MESH':
            obj = context.edit_object
            if obj and obj.type == 'MESH':
                after_selection = self.get_selected_mesh_elements(obj)
                if after_selection == before_selection and any(len(s) > 0 for s in after_selection):
                    bpy.ops.mesh.select_all(action='DESELECT')

    def get_selected_mesh_elements(self, obj):
        # 获取指定网格对象在编辑模式下当前选中的顶点、边、面索引。
        obj.update_from_editmode() # 确保编辑模式数据是最新的
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        selected_verts = {v for v in bm.verts if v.select}
        selected_edges = {e for e in bm.edges if e.select}
        selected_faces = {f for f in bm.faces if f.select}

        return (selected_verts, selected_edges, selected_faces)

    def cancel_operation(self, context):
        self.cleanup_drawing()
        context.area.tag_redraw()

    def cleanup_drawing(self):
        if self.draw_handle:
            bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle, 'WINDOW')
            self.draw_handle = None


class RARA_OT_Public_SwitchSelectTools(bpy.types.Operator):
    bl_idname = "rara.view3d_public_switch_select_tool"
    bl_label = "Cross Select Draw Mode Switch"

    def execute(self, context):
        prefs = bpy.context.preferences.addons[__package__].preferences
        if prefs.select_draw_mode == 'BOX':
            prefs.select_draw_mode = 'LASSO'
            context.area.tag_redraw()
            self.report({'INFO'}, f"Switch to Lasso Select Mode")
        else:
            prefs.select_draw_mode = 'BOX'
            context.area.tag_redraw()
            self.report({'INFO'}, f"Switch to Box Select Mode")
        return {'FINISHED'}

# ============================== 辅助工具 ==============================
class VIEW3D_PT_object_type_visibility_extended(bpy.types.Panel):
    bl_idname = "VIEW3D_PT_object_type_visibility_extended"
    bl_label = "Selectability & Visibility"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 8

    def draw(self, context):
        view = context.space_data
        layout = self.layout
        # layout.separator()
        layout.label(text="Selectability & Visibility")
        col = layout.column(align=True)

        # 动态获取获取VIEW3D_PT_object_type_visibility的attr_object_types
        from bl_ui.space_view3d import VIEW3D_PT_object_type_visibility
        consts = getattr(VIEW3D_PT_object_type_visibility, 'draw_ex').__code__.co_consts
        for const in consts:
            if isinstance(const, tuple) and len(const) > 0:
                first_item = const[0]
                if isinstance(first_item, tuple) and len(first_item) == 3:
                    attr_object_types = const
                    break

        for attr, attr_name, attr_icon in attr_object_types:
            if attr is None:
                col.separator()
                continue

            attr_s = "show_object_select_" + attr
            icon_s = 'RESTRICT_SELECT_OFF' if getattr(view, attr_s) else 'RESTRICT_SELECT_ON'
            attr_v = "show_object_viewport_" + attr
            icon_v = 'HIDE_OFF' if getattr(view, attr_v) else 'HIDE_ON'

            row = col.row(align=True)
            op = row.operator("rara.quickly_switch_object_select_attr", text=attr_name, icon=attr_icon)
            op.target_attr = attr_s
            row.separator()

            rowsub = row.row()#
            rowsub.active = getattr(view, attr_v)
            rowsub.prop(view, attr_s, text="", icon=icon_s, emboss=False)

            row.prop(view, attr_v, text="", icon=icon_v, emboss=False)

class RARA_OT_Quickly_Switch_Object_Select_Attr(bpy.types.Operator):
    bl_idname = "rara.quickly_switch_object_select_attr"
    bl_label = "Quickly Switch Object Selectability" #快速切换可选性状态
    bl_description = "Quickly switch selectability status\n\nToggle Status|Left Click\nEnable All|Shift+Left Click\nDisable All|Ctrl+Left Click\n\nDisable Others|Alt+Left Click\nEnable Others|Shift+Alt+Left Click\nDisable Others|Ctrl+Alt+Left Click\n\nToggle All|Ctrl+Shift+Alt+Left Click"
    #快速切换可选性状态\n\n切换状态|左键\n全部开启|Shift+左键\n全部关闭|Ctrl+左键\n\n关闭其他|Alt+左键\n开启其他|Shift+Alt+左键\n关闭其他|Ctrl+Alt+左键\n\n互换所有|Ctrl+Shift+Alt+左键
    target_attr: bpy.props.StringProperty()

    def invoke(self, context, event):
        space = context.space_data
        if not hasattr(space, self.target_attr):
            self.report({'ERROR'}, f"属性不存在: {self.target_attr}")
            return {'CANCELLED'}

        # 预先收集所有相关属性
        all_attrs = [a for a in dir(space) if a.startswith("show_object_select_")]
        current = getattr(space, self.target_attr)

        # 定义按键组合映射表
        ops = {
            (event.ctrl, event.shift, event.alt): {
                (True, True, True): (lambda: self.toggle_all(space, all_attrs)), # Ctrl+Shift+Alt+左键：切换所有
                (False, True, True): (lambda: self.set_others(space, self.target_attr, True)), # Shift+Alt+左键：开启其他
                (True, False, True): (lambda: self.set_others(space, self.target_attr, False)), # Ctrl+Alt+左键：关闭其他
                (False, True, False): (lambda: self.set_all(space, True)), # Shift+左键：全部开启
                (True, False, False): (lambda: self.set_all(space, False)), # Ctrl+左键：全部关闭
                (False, False, True): (lambda: self.set_others(space, self.target_attr, False)), # Alt+左键：关闭其他
            }}

        # 自动匹配按键组合并执行操作
        key_state = (event.ctrl, event.shift, event.alt)
        if key_state in ops and key_state in ops[key_state]:
            ops[key_state][key_state]()
        else:
            # 默认切换当前属性
            setattr(space, self.target_attr, not current)
        return {'FINISHED'}

    # 辅助函数集
    def toggle_all(self, space, attrs):
        for a in attrs:
            setattr(space, a, not getattr(space, a))

    def set_all(self, space, value):
        for a in dir(space):
            if a.startswith("show_object_select_"):
                setattr(space, a, value)

    def set_others(self, space, exclude_attr, value):
        setattr(space, exclude_attr, not value)
        for a in dir(space):
            if a.startswith("show_object_select_") and a != exclude_attr:
                setattr(space, a, value)

# ============================== 工具定义 ==============================
def common_draw_settings(context, layout, tool):
    layout.label(text="Cross Select Settings") #交错选择设置
    prefs = bpy.context.preferences.addons[__package__].preferences

    if prefs.select_draw_mode == 'BOX':
        layout.prop(prefs, "select_draw_mode", text="Mode", icon="MESH_PLANE")
        layout.label(text="Drag Left: Orange (Half Match)", icon='BACK') #向左拖拽: 橙色(半匹配)
        layout.label(text="Drag Right: Blue (Fully Match)", icon='FORWARD') #向右拖拽: 蓝色(完全匹配)
    else:
        layout.prop(prefs, "select_draw_mode", text="Mode", icon="MESH_CIRCLE")
        layout.label(text="Clockwise: Orange (Half Match)", icon='LOOP_FORWARDS') #顺时针: 橙色(半匹配)
        layout.label(text="Counterclockwise: Blue (Fully Match)", icon='LOOP_BACK') #逆时针: 蓝色(完全匹配)

    layout.popover(
        panel="VIEW3D_PT_object_type_visibility_extended",
        icon_value=context.space_data.icon_from_show_object_viewport,
        text="",
    )

KEYMAP = (
    ("rara.view3d_public_switch_select_tool", {"type": "W", "value": "PRESS",}, {"properties": []}),#切换选取模式 W

    ("mesh.loop_select", {"type": "LEFTMOUSE", "value": "CLICK", "alt": True,}, {"properties": []}),#环状选择
    ("mesh.edgering_select", {"type": "LEFTMOUSE", "value": "CLICK", "ctrl": True, "alt": True,}, {"properties": []}),#并排边选择
    ("mesh.shortest_path_pick", {"type": "LEFTMOUSE", "value": "CLICK", "shift": True, "alt": True,}, {"properties": []}),#最短边选择
    ("mesh.shortest_path_pick", {"type": "LEFTMOUSE", "value": "CLICK", "ctrl": True ,"shift": True, "alt": True,}, {"properties": [("use_fill", True)]}),#填充选择

    ("rara.view3d_ultimate_public_select_tool", {"type": "LEFTMOUSE", "value": "PRESS"}, {"properties": []}),
    ("rara.view3d_ultimate_public_select_tool", {"type": "LEFTMOUSE", "value": "PRESS", "shift": True}, {"properties": []}),
    ("rara.view3d_ultimate_public_select_tool", {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True}, {"properties": []}),
    ("rara.view3d_ultimate_public_select_tool", {"type": "LEFTMOUSE", "value": "PRESS", "shift": True, "ctrl": True},{"properties": []}),
)

class RARA_TL_ULTIMATE_Public_SelectTool_Obj(bpy.types.WorkSpaceTool):
    bl_idname = "rara.view3d_ultimate_public_select_tool_obj"
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_label = "Cross Select (Object Mode)" #交错选择(物体)

    bl_icon = os.path.join(os.path.dirname(__file__), "icons", "Cross_Select_Icon")
    bl_widget = None
    bl_keymap = KEYMAP

    @staticmethod
    def draw_settings(context, layout, tool):
        common_draw_settings(context, layout, tool)

class RARA_TL_ULTIMATE_Public_SelectTool_Edit(bpy.types.WorkSpaceTool):
    bl_idname = "rara.view3d_ultimate_public_select_tool_edit"
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_label = "Cross Select (Edit Mode)" #交错选择(编辑)
    bl_icon = os.path.join(os.path.dirname(__file__), "icons", "Cross_Select_Icon")
    bl_widget = None
    bl_keymap = KEYMAP

    @staticmethod
    def draw_settings(context, layout, tool):
        common_draw_settings(context, layout, tool)

# ============================== 偏好设置 ==============================
class Rara_Public_SelectToolsPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    show_debug : bpy.props.BoolProperty(
        name="Enable Debug Mode",description="For Debugging Only",default=False)
    show_info : bpy.props.BoolProperty(
        name="Expand Usage Instructions",description="View detailed usage instructions for the plugin",default=True)

    contain_line_color: bpy.props.FloatVectorProperty( #完全匹配模式色彩色值，默认蓝色
        name="Fully Match Mode Color", description="Color value for fully match mode, default blue",
        subtype='COLOR', default=(0.2, 0.6, 1.0), min=0.0, max=1.0)

    cross_line_color: bpy.props.FloatVectorProperty( #半匹配模式色彩色值，默认橙色
        name="Half Match Mode Color", description="Color value for half match mode, default orange",
        subtype='COLOR', default=(1.0, 0.4, 0.1), min=0.0, max=1.0)

    line_width: bpy.props.IntProperty(
        name="Line Width", description="Drawing Line Width", default=2, min=0, max=20)

    select_draw_mode: bpy.props.EnumProperty(
        name="Selection Mode", description="Choose Box Select or Lasso Select", #选择框选或圈选
        items=[
            ('BOX', "Box Select", "Box Select [←|Drag Left|Orange|Half Match] [→|Drag Right|Blue|Fully Match]"), #框选[←|向左拖拽|橙色|半匹配] [→|向右拖拽|蓝色|完全匹配]
            ('LASSO', "Lasso Select", "Lasso Select [↻|Clockwise|Orange|Half Match] [↺|Counterclockwise|Blue|Fully Match]"), #圈选[↻|顺时针|橙色|半匹配] [↺|逆时针|蓝色|完全匹配]
        ],default='BOX')

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, "contain_line_color",text="")
        row.label(text="Fully Match Mode",icon="STICKY_UVS_LOC")#完全匹配
        row.prop(self, "cross_line_color",text="")
        row.label(text="Half Match Mode",icon="XRAY")#半匹配

        row = layout.row()
        row.prop(self, "line_width",text="Line Width")#绘制线宽
        # layout.prop(self, "show_debug",text="DEBUG")

        box=layout.box()
        col = box.column(align=True)

        row=col.row()
        row.label(text="Usage Instructions",icon="QUESTION")
        row.prop(self, "show_info",text="",icon="DOWNARROW_HLT" if self.show_info else "RIGHTARROW",emboss=False)
        if self.show_info:
            col.separator(type="LINE")
            col.label(text="You can find this tool (Cross Select) in the tool panel (T-panel) on the left side of the 3D viewport")
            col.label(text="Currently supports cross selection in mesh edit mode and object mode")
            col.label(text="")

            col.separator(type="LINE")
            col.label(text="【Box Select Mode】: Dragging left performs a half match box select, dragging right performs a fully match box select",icon="MESH_PLANE")
            col.label(text="【Lasso Select Mode】: Drawing a lasso clockwise performs a half match lasso select, drawing counterclockwise performs a fully match lasso select",icon="MESH_CIRCLE")
            col.separator(type="LINE")
            col.label(text="【Fully Match】: In this state, only elements fully contained within the selection area will be selected",icon="STICKY_UVS_LOC")
            col.label(text="【Half Match】: In this state, any element partially touched by the selection area will be selected",icon="XRAY")
            col.label(text="")

            col.separator(type="LINE")
            col.label(text="Supported HotKey:")
            row=col.row()
            row.label(text="",icon="EVENT_SHIFT")
            row.label(text="Add Selection")
            row.label(text="",icon="EVENT_CTRL")
            row.label(text="Subtract Selection")
            row.label(text="",icon="EVENT_W")
            row.label(text="Switch Selection Mode")
            col.label(text="")

            col.label(text="Additional support in mesh mode (based on system native tools):")
            row=col.row()
            row.label(text="",icon="EVENT_ALT")
            row.label(text="Loop Select")
            row.label(text="",icon="EVENT_CTRL")
            row.label(text="",icon="EVENT_ALT")
            row.label(text="Edge Ring Select")
            row.label(text="",icon="EVENT_SHIFT")
            row.label(text="",icon="EVENT_ALT")
            row.label(text="Shortest Path Select")
            row.label(text="",icon="EVENT_SHIFT")
            row.label(text="",icon="EVENT_CTRL")
            row.label(text="",icon="EVENT_ALT")
            row.label(text="Shortest Path Fill")

            col.label(text="")

# ============================== 注册 ==============================
classes = (
    RARA_OT_ULTIMATE_Public_SelectTools,
    RARA_OT_Public_SwitchSelectTools,
    RARA_OT_Quickly_Switch_Object_Select_Attr,
    VIEW3D_PT_object_type_visibility_extended,
    Rara_Public_SelectToolsPreferences,
)

def register():
    translation.register()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.utils.register_tool(RARA_TL_ULTIMATE_Public_SelectTool_Obj, separator=True)
    bpy.utils.register_tool(RARA_TL_ULTIMATE_Public_SelectTool_Edit, separator=True)

def unregister():
    translation.unregister()
    bpy.utils.unregister_tool(RARA_TL_ULTIMATE_Public_SelectTool_Obj)
    bpy.utils.unregister_tool(RARA_TL_ULTIMATE_Public_SelectTool_Edit)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if bpy.app.background:
    print("\n---------------------------------")
    print(f"{bl_info['name']}_V{bl_info['version']}后台模式忽略加载")
    print("---------------------------------\n")
    def register():
        pass
    def unregister():
        pass

if __name__ == "__main__":
    register()


