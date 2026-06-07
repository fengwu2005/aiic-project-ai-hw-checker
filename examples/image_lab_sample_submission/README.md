# ImageLab 作业提交说明

这是一个命令行图像变换工具。程序入口是 `final/image_ops.py`，核心依赖是 Pillow/PIL。

## 功能清单

- 读取图片并统一转换为 RGB 模式
- 保存图片到目标路径
- 按比例放大和缩小图片
- 按角度旋转图片
- 按坐标裁剪图片
- 反色处理
- 3x3 均值模糊
- 固定卷积核边缘提取
- 中值滤波
- 统一命令行调度入口
- 对非法缩放比例、非法裁剪框、非法滤波尺寸和未知操作抛出明确错误

## 运行示例

```bash
python final/image_ops.py input.png output.png invert
python final/image_ops.py input.png output.png resize --scale 2
python final/image_ops.py input.png output.png rotate --angle 90
python final/image_ops.py input.png output.png crop --box 10,10,120,120
python final/image_ops.py input.png output.png median --size 3
```

## 自查方式

我用小尺寸 RGB 图片检查了：

- `resize_image` 是否按比例改变尺寸
- `crop_image` 是否返回正确区域
- `invert_image` 是否把黑色变白色
- `blur_image` 是否降低孤立亮点强度
- `edge_detect` 是否让边缘区域比平坦区域更亮
- `median_filter` 是否移除孤立噪点

## 已知限制

- 当前版本主要处理 RGB 图像，透明通道会在读取后转为 RGB。
- 模糊和边缘检测使用固定 3x3 窗口，速度适合课程规模图片，不适合超大图批处理。
- 命令行只支持单步变换，多步流水线可以作为后续扩展。

## 报告说明

详细实现方法、验证方式、关键贡献和已知不足见 `report/report.md`。
