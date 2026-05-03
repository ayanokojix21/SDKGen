from langchain_core.runnables import RunnableLambda

def fail_1(x):
    print("Trying 1...")
    raise ValueError("1 failed")

def fail_2(x):
    print("Trying 2...")
    raise ValueError("2 failed")

def succeed_3(x):
    print("Trying 3...")
    return "3 succeeded!"

r1 = RunnableLambda(fail_1)
r2 = RunnableLambda(fail_2)
r3 = RunnableLambda(succeed_3)

chain = r1.with_fallbacks([r2, r3])
print(chain.invoke("test"))
