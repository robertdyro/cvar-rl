from __future__ import division
from __future__ import print_function
import tensorflow as tf
import numpy as np

def random_scope():
  return str(np.random.randint(np.iinfo(np.int64).max))

def pred_op(in_, layerN, scope, out_nb, keep_prob=None):
  with tf.variable_scope(scope, reuse=tf.AUTO_REUSE):
    nn_ = in_
    # hidden layers
    for i in range(len(layerN)):
      nn_ = tf.layers.dense(nn_, layerN[i], activation=tf.nn.tanh)
      nn_ = nn_ if keep_prob == None else tf.nn.dropout(nn_, keep_prob)
    # output layer
    nn_ = tf.layers.dense(nn_, out_nb, activation=tf.identity)
  return nn_

def assign_op(scope_to, scope_from):
  vars_to = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope=scope_to)
  vars_from = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES,
      scope=scope_from)
  assert len(vars_to) == len(vars_from)
  ops = [tf.assign(vars_to[i], vars_from[i]) for i in range(len(vars_to))]
  return tf.group(*ops)

def loss_op(v1_, v2_):
  return tf.reduce_mean(tf.squared_difference(v1_, v2_))

"""
def optimizer_op(loss_, scope, lr, clip_gradient=None):
  adam = tf.train.AdamOptimizer(learning_rate=lr)
  s_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope=scope)
  gs_vs = adam.compute_gradients(loss_, var_list=s_vars)
  gs = [el[0] for el in gs_vs]
  vs = [el[1] for el in gs_vs]
  if clip_gradient != None:
    gs = [tf.clip_by_norm(el, clip_gradient) for el in gs]
    gs_vs = list(zip(gs, vs))
  train_op = adam.apply_gradients(gs_vs)
  grad_norm = tf.global_norm(gs)
  return (train_op, grad_norm)
"""

def optimizer_op(loss_, lr):
  adam = tf.train.AdamOptimizer(learning_rate=lr)
  train_op = adam.minimize(loss_)
  return train_op

def batch_idx(n, N, min_nb=100):
  n = max(int(np.ceil(n)), min_nb)
  N = int(np.ceil(N))
  return np.random.randint(N, size=n) if n <= N else np.arange(N)

def train_till_convergence_or_for(sess, loss_, train_, plhs, vals,
    is_data=True, **kwargs):
  assert len(plhs) == len(vals)
  kwargs = dict({"winN": 50, "min_nb": 100, "times": -1, "batch_frac": 0.01},
      **kwargs)
  is_data = np.repeat(is_data, len(plhs)) if np.size(is_data) == 1 else is_data

  winN = kwargs["winN"]
  times = kwargs["times"]
  lh = np.zeros(winN) # loss history
  i = 0
  N = vals[0].shape[0]

  while i < winN or np.mean(lh[0:(winN // 2)] - lh[(winN // 2):]) >= 0.0:
    idx = batch_idx(kwargs["batch_frac"] * N, N, kwargs["min_nb"])
    feed_dict = {}
    for i in range(len(vals)):
      if is_data[i]:
        if len(np.shape(vals[i])) == 1:
          feed_dict[plhs[i]] = vals[i][idx]
        elif len(np.shape(vals[i])) == 2:
          feed_dict[plhs[i]] = vals[i][idx, :]
        else:
          raise NotImplementedError
      else:
        feed_dict[plhs[i]] = vals[i]
    #feed_dict = dict(zip(plhs, [vals[i][idx, :] if is_data[i] else vals[i] for
    #i in range(len(vals))]))
    (loss, _) = sess.run([loss_, train_], feed_dict=feed_dict)
    lh[0:-1] = lh[1:]
    lh[-1] = loss
    i += 1
    if times == 0:
      break
    times -= 1
