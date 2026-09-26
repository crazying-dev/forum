# -*- coding: utf-8 -*-
"""动作文件统计字段重算（原样移植自 ``lpk2moc3/motion_spec.py``）。

唯一改动：遇到无法识别的 segment 标识符时抛 :class:`ValueError`，
避免 ``while v < end_pos`` 因为 ``v`` 不前进而死循环（上游更新版同样如此处理）。
"""

from __future__ import annotations


def recount_motion(motion: dict) -> tuple[int, int, int]:
    """
    recount curveCount, TotalSegmentCount and TotalPointCount in model3.json
    """
    segment_count = 0
    point_count = 0
    curves = motion["Curves"]
    curve_count = len(curves)
    for curve in curves:
        segments = curve["Segments"]
        end_pos = len(segments)
        point_count += 1
        v = 2
        while v < end_pos:
            identifier = segments[v]
            if identifier == 0 or identifier == 2 or identifier == 3:
                point_count += 1
                v += 3
            elif identifier == 1:
                point_count += 3
                v += 7
            else:
                raise ValueError("unknown segment identifier: %r" % (identifier,))
            segment_count += 1
    return curve_count, segment_count, point_count
