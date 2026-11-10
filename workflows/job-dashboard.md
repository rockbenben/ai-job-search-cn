# /job-dashboard —— 打开本机求职总览

服务当前用户，默认端口 29029。

## 执行

1. 直接执行，等命令返回结果：

   ```bash
   python tools/serve.py --background
   ```

2. 成功时简短告知结果并附上输出中的可点击地址；浏览器未打开时说「总览已启动」。
   失败时按错误处理。启动、复用、就绪检查与打开浏览器均由脚本负责。

## 参数

可选参数：用户名转为服务的 `--user`，端口转为 `--port`。

- `/job-dashboard <用户名>` → `python tools/serve.py --background --user "<用户名>"`。
- `/job-dashboard --port 8080` → `python tools/serve.py --background --port 8080`。

## 仅在服务报错时处理

- 缺前端产物时，执行 `cd web && npm install && npm run build`，完成后再次启动服务。
- 旧代码需要重启时按服务输出处理；启动超时先查输出中的日志。
- 端口属于其他程序或用户时，用 `python tools/serve.py --background --port <空闲端口>`，指定用户时保留 `--user` 参数，保留原进程。
- 用户或职位库缺失时，按服务提示给出对应的完整命令：未建档引导跑 `/job-setup`；活动用户指向不存在的目录时引导跑 `/job-user`；职位库缺失时引导跑 `/job-auto`。

## 执行边界

启动前跳过资料读取、自检和额外预检查。服务按需调用 `export_web_data.py` 自动更新当前用户的 `data.json`，刷新浏览器即最新，无需手动重导数据。
总览只在本机访问，状态按钮直接写回；不上传数据，不例行介绍面板功能。
