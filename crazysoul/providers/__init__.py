"""[3] Image Provider Layer 與 [5a] Video Provider Layer。

Phase 0 只接一家(Flux / Kling via fal.ai),先跑通再抽象——
所以這裡還不是完整的統一介面,只是把「呼叫哪一家」收在同一層,
之後 Phase 3 再包成 image.generate() / video.generate() 的正式抽象。
"""
