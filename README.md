# 冬日绘板脚本免费送
功能：将本地的图片 ping 到绘版上。相较于完整版，不会进行维护且 token 并行上限锁定至 10。

安装必要库（参考 pre.txt），如果本地没有 python 环境，先配置 python 环境。

按照 [Uid]空格[AccessKey] 格式放到 access_local 里。

C++ 运行 local_to_final

图片名称 image.png

调整 config.py 里面的参数（冷却，位置，缩放等）并将 access_final 的内容放到 config.py 对应位置。

运行 自动.cpp ，将会自动画，防止其他人破坏。

还有不理解的或者编译时报错（大概率是 python 或库版本不对）可以问 AI。

来源：https://www.luogu.com.cn/problem/U624334
