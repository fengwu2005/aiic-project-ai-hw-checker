# ImageLab 学生报告

## 实现方法

我实现了 `load_image`、`save_image`、`resize_image`、`rotate_image`、`crop_image` 和 `invert_image`，也保留了 `blur_image`、`edge_detect`、`median_filter` 这些固定函数名。命令行入口可以调用部分操作。

## 验证方法

我主要验证了图片能读取保存、缩放后尺寸变化、裁剪能得到区域、反色能改变颜色。对于均值模糊、边缘检测和中值滤波，我还没有做像素级验证。

## 已知不足

滤波函数目前实现得比较粗糙，边缘检测没有真正写卷积核，中值滤波没有计算窗口中位数。参数校验也不完整，例如非法缩放比例和非法裁剪框需要继续补。
