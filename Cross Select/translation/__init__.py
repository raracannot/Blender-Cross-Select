
#blender 多语言支持通用模块（ONLY）
#2025/08/08

#===============================================================================
# HOW_TO_USE（使用说明）
#===============================================================================

# 一、目录结构建议
#
# your_addon/
# ├── __init__.py                # 插件主入口
# ├── translation/               # 多语言目录
# │   ├── __init__.py            # 本文件，负责自动注册所有语言
# │   ├── zh_HANS.py             # 简体中文语言包
# │   ├── en_US.py               # 英文语言包
# │   └── ...                    # 其它语言包（如 fr_FR.py、ja_JP.py 等）

#以Blender 4.5为例，已支持语言包：
#('DEFAULT', 'ab', 'ar_EG', 'eu_EU', 'be', 'bg_BG', 'ca_AD', 'zh_HANS', 'zh_HANT', 'hr_HR', 'cs_CZ', 'da', 'nl_NL', 'en_GB', 'en_US', 'eo', 'fi_FI', 'fr_FR', 'ka', 'de_DE', 'el_GR', 'ha', 'he_IL', 'hi_IN', 'hu_HU', 'id_ID', 'it_IT', 'ja_JP', 'km', 'ko_KR', 'ky_KG', 'lt', 'ne_NP', 'fa_IR', 'pl_PL', 'pt_BR', 'pt_PT', 'ro_RO', 'ru_RU', 'sr_RS', 'sr_RS@latin', 'sk_SK', 'sl', 'es', 'sw', 'sv_SE', 'ta', 'th_TH', 'tr_TR', 'uk_UA', 'ur', 'vi_VN')

# 二、每个语言包文件示例（如 translation/zh_HANS.py）
#
# data = {
#     "Hello": "你好",
#     "World": "世界",
#     # 更多原文与翻译对
# }

# 三、插件主入口示例（your_addon/__init__.py）
#
# from . import translation
#
# def register():
#     translation.register()
#
# def unregister():
#     translation.unregister()
#
# # Blender 将自动调用 register/unregister 以加载/卸载插件

# 四、如何添加新的语言支持？
#
# 1. 在 translation 目录下新建一个语言文件，文件名必须与 Blender 支持的语言代码一致
# 2. 在该文件中定义 data 字典，键为原文，值为翻译
# 3. 修改本文件开始处的langs代码，插件会依据langs注册新语言

# 五、注意事项
#
# - 语言文件名必须与 Blender 支持的语言代码一致，否则不会被自动注册
# - 每个语言文件必须有 data 字典
# - translation/__init__.py 不需要手动修改，只需确保语言包文件正确即可
# - 可通过取消注释 print(all_languages) 查看 Blender 当前支持的语言代码
# - 如果翻译语句中包含\n转义符如："test\ntest"，需将其以三引号包裹如："""test\ntest"""

#===============================================================================

import re
import ast
import bpy

from . import zh_HANS
from . import en_US
# 其他语言请至此导入

TRANSLATION_DOMAIN = "rara_blender_helper" #翻译唯一标识
langs = {
    "zh_CN": zh_HANS.data, #旧版blender简中标识符
    "zh_HANS": zh_HANS.data,
    "en_GB": en_US.data,
    "en_US": en_US.data,
    # 其他语言请至此添加
}

# 获取Blender支持的语言列表，利用异常信息（TypeError）间接获取 Blender 支持的语言列表
def get_language_list() -> list:
    try:
        bpy.context.preferences.view.language = ""
    except TypeError as e:
        matches = re.findall(r"\(([^()]*)\)", e.args[-1])
        return ast.literal_eval(f"({matches[-1]})")

# 翻译辅助类
class TranslationHelper():
    def __init__(self, data: dict, lang='zh_HANS'):
        self.name = TRANSLATION_DOMAIN
        self.translations_dict = dict()

        for src, src_trans in data.items():
            key = ("Operator", src)
            self.translations_dict.setdefault(lang, {})[key] = src_trans
            key = ("*", src)
            self.translations_dict.setdefault(lang, {})[key] = src_trans
            key = (self.name, src)
            self.translations_dict.setdefault(lang, {})[key] = src_trans

    def register(self):
        try:
            bpy.app.translations.register(self.name, self.translations_dict)
        except(ValueError):
            pass

    def unregister(self):
        bpy.app.translations.unregister(self.name)

I18N = {}
    
def register():
    global I18N
    all_languages = get_language_list()
    # print(all_languages)

    for lang_code, data in langs.items():
        if lang_code in all_languages:
            helper = TranslationHelper(data, lang=lang_code)
            helper.register()
            I18N[lang_code] = helper

def unregister():
    for helper in I18N.values():
        helper.unregister()
    I18N.clear()
    
    
    
