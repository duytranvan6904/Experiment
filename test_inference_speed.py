import time
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model

model = load_model('/home/duy/Downloads/GRU-Model-main/gru_velocity_3_layers.h5', compile=False, custom_objects={'GRU': tf.keras.layers.GRU})

# dummy data
inputs = np.zeros((1, 20, 3), dtype=np.float32)

def test_time(name, func, runs=10):
    # warmup
    for _ in range(2): func()
    t0 = time.time()
    for _ in range(runs): func()
    avg = (time.time() - t0) * 1000 / runs
    print(f"{name}: {avg:.2f} ms")

test_time("predict", lambda: model.predict(inputs, verbose=0))
test_time("predict_on_batch", lambda: model.predict_on_batch(inputs))
test_time("call", lambda: model(inputs, training=False))

@tf.function(jit_compile=True)
def jitted(x): return model(x, training=False)
test_time("jitted", lambda: jitted(tf.constant(inputs)))
