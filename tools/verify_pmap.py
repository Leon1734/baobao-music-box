"""验证 _pmap 的硬截止行为 —— 优化前搜索最坏 78 秒，优化后必须被 deadline 卡住。

测的就是「一个慢到离谱的源会不会拖死整个请求」：
  优化前（as_completed(timeout=18) + 串行兜底）：
     18s 超时 → 串行重跑 4 个慢源 → 最坏 18 + 4×15 = 78 秒
  优化后（_pmap 硬截止）：
     到 deadline 直接补空返回，慢源的线程收尾不等（cancel_futures=True）
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "mbserver", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server.py"))
mb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mb)


def main():
    srv = mb.H.__new__(mb.H)      # 不启动 HTTP，只拿方法（类名是 H）

    print("========== _pmap 硬截止验证 ==========")

    # ① 3 个快源 + 2 个慢到 30 秒的源，deadline=3s
    def slow(a):
        def f():
            time.sleep(a)
            return ["slow_%d" % a]
        return f
    fn = {"fast1": lambda: ["A1", "A2"], "fast2": lambda: ["B1"],
          "slow30": slow(30), "slow30b": slow(30)}
    t0 = time.time()
    res = srv._pmap(fn, deadline=3.0)
    dt = time.time() - t0
    ok_bound = dt < 5.0
    ok_fast = (res.get("fast1") == ["A1", "A2"]) and (res.get("fast2") == ["B1"])
    ok_slow_empty = (res.get("slow30") == []) and (res.get("slow30b") == [])
    print(f"  ① 2 快 + 2 慢(30s) / deadline=3s")
    print(f"     实际耗时 {dt:.2f}s   要求 <5s     {'✅' if ok_bound else '❌ 超出上限'}")
    print(f"     快源结果保留              {'✅' if ok_fast else '❌ 丢了'}")
    print(f"     慢源被补空（不拖住）       {'✅' if ok_slow_empty else '❌ 不为空'}")

    # ② 全部慢源：确保也是硬截止，不是等到全部跑完
    fn2 = {"a": slow(25), "b": slow(25), "c": slow(25), "d": slow(25)}
    t0 = time.time()
    res2 = srv._pmap(fn2, deadline=2.0)
    dt2 = time.time() - t0
    ok2 = dt2 < 4.0 and all(res2[k] == [] for k in fn2)
    print(f"\n  ② 4 个全慢(25s) / deadline=2s")
    print(f"     实际耗时 {dt2:.2f}s   要求 <4s     {'✅' if ok2 else '❌'}")

    # ③ 单源短路（不开线程池）
    t0 = time.time()
    res3 = srv._pmap({"only": lambda: ["X"]}, deadline=1.0)
    dt3 = time.time() - t0
    ok3 = res3 == {"only": ["X"]} and dt3 < 1.0
    print(f"\n  ③ 单源短路  {dt3:.3f}s  结果={res3}   {'✅' if ok3 else '❌'}")

    # ④ 异常源不能拖垮整体
    def boom():
        raise RuntimeError("模拟源挂了")
    fn4 = {"good": lambda: ["OK"], "bad": boom}
    t0 = time.time()
    res4 = srv._pmap(fn4, deadline=2.0)
    dt4 = time.time() - t0
    ok4 = res4.get("good") == ["OK"] and res4.get("bad") == [] and dt4 < 2.0
    print(f"\n  ④ 异常源隔离  {dt4:.2f}s  结果={res4}   {'✅' if ok4 else '❌'}")

    # ⑤ 宽限期早返回：1 慢源(30s) 拖着，grace=2s 应在 ~2s 返回，而不是干等到 8s
    #    （复用上面定义的 slow()，不重复声明）
    fn5 = {"fast": lambda: ["FA"], "slow30": slow(30), "slow30b": slow(30)}
    t0 = time.time()
    res5 = srv._pmap(fn5, deadline=8.0, grace=2.0)
    dt5 = time.time() - t0
    ok5 = (dt5 < 4.0) and (res5.get("fast") == ["FA"]) and (res5.get("slow30") == [])
    print(f"\n  ⑤ 宽限期早返回  实际 {dt5:.2f}s（deadline=8 但 grace=2）要求 <4s   {'✅' if ok5 else '❌'}")
    print(f"     快源保留={res5.get('fast')}  慢源补空={res5.get('slow30')}")
    print(f"     对比：不加 grace 时这里会卡满 8 秒（实测榜单 8111ms 就是这么来的）")

    print()
    all_ok = ok_bound and ok_fast and ok_slow_empty and ok2 and ok3 and ok4 and ok5
    print("✅ 硬截止生效，优化前最坏 78 秒 → 现在恒定 <deadline" if all_ok
          else "❌ 硬截止未生效，回退方案失败")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
