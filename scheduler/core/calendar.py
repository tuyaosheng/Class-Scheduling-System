"""时间格与节次口径。

全系统唯一的「星期/节次 <-> 扁平索引」换算入口。
下午第 N 节 = 第 5+N 节，这个口径写错会让所有禁排规则整体偏移。
"""

DAYS = ['周一', '周二', '周三', '周四', '周五']
PERIODS_PER_DAY = 9
N_SLOTS = len(DAYS) * PERIODS_PER_DAY

MORNING = (1, 2, 3, 4, 5)
AFTERNOON = (6, 7, 8, 9)

_DAY_TO_INDEX = {name: i for i, name in enumerate(DAYS)}


def day_index(name):
    try:
        return _DAY_TO_INDEX[name]
    except KeyError:
        raise ValueError('未知星期：%r，仅支持 %s' % (name, DAYS))


def slot_index(day, period):
    if not 0 <= day < len(DAYS):
        raise ValueError('星期序号越界：%s' % day)
    if not 1 <= period <= PERIODS_PER_DAY:
        raise ValueError('节次越界：%s' % period)
    return day * PERIODS_PER_DAY + (period - 1)


def slot_of(index):
    if not 0 <= index < N_SLOTS:
        raise ValueError('时间格索引越界：%s' % index)
    return index // PERIODS_PER_DAY, index % PERIODS_PER_DAY + 1


def section_period(section, n):
    """把「上午/下午第 n 节」换算为绝对节次。section 为 None 时 n 即绝对节次。"""
    if section == '上午':
        if n not in MORNING:
            raise ValueError('上午只有 1-5 节，收到第 %s 节' % n)
        return n
    if section == '下午':
        if not 1 <= n <= len(AFTERNOON):
            raise ValueError('下午只有 1-4 节，收到第 %s 节' % n)
        return len(MORNING) + n
    if section is None:
        if not 1 <= n <= PERIODS_PER_DAY:
            raise ValueError('节次越界：%s' % n)
        return n
    raise ValueError('未知时段：%r' % section)
