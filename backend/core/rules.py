def rule_based_hr(hr):
    if hr < 40:
        return "DANGER_LOW", "Nhịp tim quá thấp"
    elif hr < 60:
        return "LOW", "Nhịp tim thấp"
    elif hr <= 100:
        return "NORMAL", "Nhịp tim bình thường"
    elif hr <= 130:
        return "HIGH", "Nhịp tim cao"
    else:
        return "DANGER_HIGH", "Nhịp tim quá cao"
    return "UNKNOWN", "Giá trị nhịp tim không xác định" 

# cảnh báo xu hướng
def trend_warning(hr_list):
    if len(hr_list) < 5:
        return None

    if all(hr > 120 for hr in hr_list[-5:]):
        return "HR cao kéo dài"

    return None
