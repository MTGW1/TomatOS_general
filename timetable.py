import asyncio
import os
import json
import signal
from datetime import datetime, timedelta
from logger import logger
import sys

AppShutdownTimeDelta = 3 * 60  # seconds # 关机缓冲时间, 避免过快关机导致任务丢失(到时候学校就会断电)
WeekdayPoweroffTimetable = "56 22 * * * 0-4"  # 每天22点56分关机 (周日到周四)
WeekendPoweroffTimetable = "26 23 * * * 5-6"  # 每天23点26分关机 周五周六

self_path = os.path.abspath(__file__)
base_dir = os.path.dirname(self_path)
AppStartPath = os.path.join(base_dir, "start_TomatOS.sh")  # TomatOS 启动脚本路径

# 进程表
progress_json_path = os.path.join(base_dir, "progress.json")
progress_base = {
    "pid" : 0,             # 进程ID
    "filepath" : "",       # 进程文件路径
    "status" : "stopped"   # 进程状态(running/stopped)
}

# 任务表
task_json_path = os.path.join(base_dir, "task.json")
task_base = {
    "tasks": [],
    "start_time": None,
    "logfile": os.path.join(base_dir, "task.log")
}

async def safe_poweroff(force = False, restart=False):
    """安全关机函数，等待缓冲时间后执行关机(缓冲期内关闭完进程也会关机), 在此期间会安全关闭所有计划任务"""
    now = datetime.now()
    now_weekday = now.weekday()  # 星期几 0-6 对应 周一到周日
    if now_weekday <= 4:
        poweroff_time_delta = datetime.strptime("22:56:00", "%H:%M:%S").time()
    else:
        poweroff_time_delta = datetime.strptime("23:26:00", "%H:%M:%S").time()

    poweroff_time = datetime.combine(now.date(), poweroff_time_delta)
    force_time = poweroff_time + timedelta(seconds=AppShutdownTimeDelta)

    # 如果还没到关机时间，直接返回
    if now < poweroff_time and not force:
        wait_time = (poweroff_time - now).total_seconds()
        logger.info(f"当前时间未到关机时间，等待 {int(wait_time)} 秒后再尝试关机...")
        await asyncio.sleep(wait_time)

    logger.info(f"系统将在 {poweroff_time.strftime('%Y-%m-%d %H:%M:%S')} 关机，缓冲时间至 {force_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 尝试关闭程序
    pid = 0
    try:
        p_path = os.path.expanduser(progress_json_path)
        if os.path.exists(p_path):
            with open(p_path, 'r') as f:
                prog = json.load(f)
                pid = prog.get('pid', 0)
    except Exception as e:
        logger.error(f"读取进程表失败: {e}")

    if pid > 0:
        try:
            # 检查进程是否存在
            os.kill(pid, 0)
            logger.info(f"向进程 {pid} 发送 SIGTERM 信号以请求关闭...")
            os.kill(pid, signal.SIGTERM)
            
            # 等待进程结束或直到强制关机时间
            while datetime.now() < force_time:
                try:
                    os.kill(pid, 0) # 检查进程还在不在
                    await asyncio.sleep(1)
                except OSError:
                    logger.info("进程已优雅退出。")
                    break
            else:
                logger.warning("缓冲时间已超出，强制关机。")
        except OSError:
            logger.info("进程未运行。")
    
    # 执行关机
    logger.info("系统正在关机。")
    if restart:
        os.system("reboot")
    else:
        os.system("shutdown now")

def main():
    # 获取运行参数
    args = sys.argv[1:]
    if len(args) > 0:
        arg = args[0]
        # 支持带--的参数
        if arg.startswith("--"):
            arg = arg[2:]
        
        if arg == "poweroff":
            asyncio.run(safe_poweroff())
        elif arg == "start":
            start_path = os.path.expanduser(AppStartPath)
            logger.info(f"正在执行启动脚本: {start_path}")
            os.system(f"bash {start_path}")
        elif arg == "restart":
            # 检测是否sudo权限
            if os.geteuid() != 0:
                logger.error("重启操作需要sudo权限，请以root用户运行此脚本。")
                return
            else:
                asyncio.run(safe_poweroff(restart=True, force=True))
        else:
            logger.error(f"未知参数: {args[0]}")
            logger.info("可用参数: poweroff, start, restart (或--poweroff, --start, --restart)")
    else:
        logger.error("请提供参数")
        logger.info("用法: python timetable.py [poweroff|start|restart]")
        logger.info("或: python timetable.py [--poweroff|--start|--restart]")
def test_restart():
    """测试重启功能"""
    logger.info("测试重启功能...")
    asyncio.run(safe_poweroff(force=True))

if __name__ == "__main__":
    main()