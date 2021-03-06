from __future__ import division
from __future__ import print_function

from util import *
from tf_util import *
import val
import env
import mod
import pol
import time

# Solver ######################################################################
class Solver:
  def __init__(self, environment, policy):
    self.environment = environment
    self.policy = policy

  def iterate(self):
    raise NotImplementedError

class TabularDiscreteSolver(Solver):
  def __init__(self, environment, policy, n):
    super().__init__(environment, policy)
    self.value_function = val.TabularValueFunction(environment.smin,
        environment.smax, n)
    self.environment = env.DiscreteEnvironment(environment, n)
    self.all_s = self.environment.all_states()
    self.policy.set_environment(self.environment)
    self.policy.set_value_function(self.value_function)

  def iterate(self):
    a = self.policy.choose_action(self.all_s)
    expected_v = self.value_function.qvalue(self.environment, self.all_s, a)
    dv = self.value_function.set_value(self.all_s, expected_v)

    return dv

class ModelDiscreteSolver(Solver):
  def __init__(self, environment, policy, n, model_str, **kwargs):
    super().__init__(environment, policy)
    self.params = dict({"h": 1e-3, "layerN": np.repeat(32, 2), "order": 10,
      "mix": True, "sample": True, "sample_nb": 10 * 10**environment.sdim},
      **kwargs)

    if model_str == "nn":
      model = mod.NNModel(environment.sdim, environment.adim,
          self.params["layerN"])
      sess = tf.Session()
      sess.run(tf.global_variables_initializer())
      model.set_session(sess)
    elif model_str == "polyls":
      model = mod.PolyLSModel(environment.sdim, environment.adim,
          self.params["order"], mix=self.params["mix"])
    else:
      raise NotImplementedError

    self.value_function = val.ModelValueFunction(environment.smin,
        environment.smax, model)
    self.environment = env.DiscreteEnvironment(environment, n)
    if self.params["sample"]:
      self.all_s = self.environment.sample_states(self.params["sample_nb"])
    else:
      self.all_s = self.environment.all_states()
    self.policy.set_environment(self.environment)
    self.policy.set_value_function(self.value_function)

  def iterate(self):
    a = self.policy.choose_action(self.all_s)
    expected_v = self.value_function.qvalue(self.environment, self.all_s, a)
    dv = self.value_function.set_value(self.all_s, expected_v)

    return dv

class PolicyGradientDiscreteSolver(Solver):
  def __init__(self, environment, n, **kwargs):
    self.params = dict({"episodes_nb": 100, "episode_len": 200, "baseline":
      False, "normalize_adv": False, "h": 3e-2, "layerN": np.repeat(32, 2),
      "scope": None, "baseline_scope": None}, **kwargs)
    policy = pol.SoftmaxPolicy(environment.sdim, environment.adim,
        environment.amin, environment.amax, n, layerN=self.params["layerN"],
        h=self.params["h"])
    self.sess = tf.Session()
    super().__init__(environment, policy)

    self.s_ = tf.placeholder(tf.float32, shape=(None, self.environment.sdim))
    
    if self.params["baseline"] == True:
      self.b_scope = (random_scope() if self.params["baseline_scope"] is None
          else self.params["baseline_scope"])
      self.b_ = pred_op(self.s_, self.params["layerN"], self.b_scope, 1)
      self.b_target_ = tf.placeholder(tf.float32, shape=(None, 1))
      self.b_loss_ = loss_op(self.b_target_, self.b_)
      self.b_train_ = optimizer_op(self.b_loss_, self.params["h"])

    self.sess.run(tf.global_variables_initializer())
    policy.set_session(self.sess)

  def _mc_gt(self, r):
    gamma = self.environment.gamma**np.arange(r.shape[2]).reshape((1, 1, -1))
    gt = np.cumsum((r * gamma)[:, :, ::-1], axis=2)[:, :, ::-1] / gamma
    return gt

  def _episodes(self):
    N = self.params["episodes_nb"]
    batch = self.params["episode_len"] * self.params["episodes_nb"]

    S = []
    A = []
    R = []
    t = 0
    while t <= batch:
      s = self.environment.sample_states(1)
      S.append(s)
      A.append(np.zeros((1, self.environment.adim, 0)))
      R.append(np.zeros((1, 1, 0)))
      done = False
      ep_len = 0
      while done == False and ep_len < self.params["episode_len"]:
        s = S[-1]
        a = A[-1]
        r = R[-1]
        cs = s[:, :, -1]

        na = self.policy.choose_action(cs)
        (ns, p) = self.environment.next_state_sample(cs, na)
        nr = self.environment.reward(cs, na, ns)

        done = self.environment.is_terminal(ns)

        a = np.dstack([a, na])
        s = np.dstack([s, ns])
        r = np.dstack([r, nr])

        S[-1] = s
        A[-1] = a
        R[-1] = r

        t += 1
        ep_len += 1

    print(self.params["episode_len"])

    # delete last state
    for j in range(len(S)):
      s = S[j]
      s = s[:, :, :-1]
      S[j] = s
    GT = [self._mc_gt(R[j]) for j in range(len(S))]
    #print("GT[j] = ", GT[0])

    """
    # print("Rendering a single episode")
    s = S[0].transpose((2, 1, 0))
    a = A[0].transpose((2, 1, 0))
    r = R[0].transpose((2, 1, 0))
    for i in range(s.shape[0]):
      self.environment.render(s[i, :, :])
      time.sleep(1.0 / 60.0)
    print("Done rendering a single episode")
    """

    """
    s = S[0].transpose((2, 1, 0))
    a = A[0].transpose((2, 1, 0))
    r = R[0].transpose((2, 1, 0))
    for i in range(s.shape[0]):
      print(i, end="")
      print(" -> ", end="")
      print(s[i, :, :].reshape(-1), end="")
      print(" -> ", end="")
      print(a[i, :, :].reshape(-1), end="")
      print(" -> ", end="")
      print(r[i, :, :].reshape(-1), end="")
      print()
    """

    for j in range(len(S)):
      assert S[j].shape[2] == A[j].shape[2]
      assert A[j].shape[2] == GT[j].shape[2]

    s = np.vstack([s.transpose((2, 1, 0)) for s in S])
    a = np.vstack([a.transpose((2, 1, 0)) for a in A])
    gt = np.vstack([gt.transpose((2, 1, 0)) for gt in GT])
    episode_lens = np.array([GT[j].size for j in range(len(S))])
    return (s, a, gt, episode_lens)

  def iterate(self):
    (s, a, gt, episode_lens) = self._episodes()
    episode_idx = np.hstack([[0], np.cumsum(episode_lens)[0:-1]])
    adv = gt
    if self.params["baseline"] == True:
      print("Training baseline")
      (s, layer_nb) = unstack2D(s)
      (gt, _) = unstack2D(gt)

      b = self.sess.run(self.b_, feed_dict={self.s_: s})
      train_till_convergence_or_for(self.sess, self.b_loss_, self.b_train_,
          [self.s_, self.b_target_], [s, gt], times=200)

      b = stack2D(b, layer_nb)
      s = stack2D(s, layer_nb)
      gt = stack2D(gt, layer_nb)
      adv = adv - b
    if self.params["normalize_adv"] == True:
      print("Normalizing advantage")
      adv -= np.mean(adv)
      adv /= np.std(adv)
    self.policy.train(s, a, adv, 1)
    print(np.mean(episode_lens))
    return np.mean(gt[episode_idx])

class PolicyGradientContinuousSolver(Solver):
  def __init__(self, environment, **kwargs):
    self.params = dict({"episodes_nb": 100, "episode_len": 200, "baseline":
      False, "normalize_adv": False, "h": 1e-2, "layerN": np.repeat(16, 2),
      "scope": None, "baseline_scope": None}, **kwargs)
    policy = pol.GaussianPolicy(environment.sdim, environment.adim,
        environment.amin, environment.amax, h=self.params["h"],
        layerN=self.params["layerN"])
    self.sess = tf.Session()
    super().__init__(environment, policy)

    self.s_ = tf.placeholder(tf.float32, shape=(None, self.environment.sdim))
    
    if self.params["baseline"] == True:
      self.b_scope = (random_scope() if self.params["baseline_scope"] is None
          else self.params["baseline_scope"])
      self.b_ = pred_op(self.s_, self.params["layerN"], self.b_scope, 1)
      self.b_target_ = tf.placeholder(tf.float32, shape=(None, 1))
      self.b_loss_ = loss_op(self.b_target_, self.b_)
      self.b_train_ = optimizer_op(self.b_loss_, self.params["h"])

    self.sess.run(tf.global_variables_initializer())
    policy.set_session(self.sess)

  def _mc_gt(self, r):
    gamma = self.environment.gamma**np.arange(r.shape[2]).reshape((1, 1, -1))
    gt = np.cumsum((r * gamma)[:, :, ::-1], axis=2)[:, :, ::-1] / gamma
    return gt

  def _episodes(self):
    N = self.params["episodes_nb"]
    batch = self.params["episodes_nb"] * self.params["episode_len"]
    S = []
    A = []
    R = []
    t = 0
    while t <= batch:
      s = self.environment.sample_states(1)
      S.append(s)
      A.append(np.zeros((1, self.environment.adim, 0)))
      R.append(np.zeros((1, 1, 0)))
      done = False
      ep_len = 0
      while done == False and ep_len < self.params["episode_len"]:
        s = S[-1]
        a = A[-1]
        r = R[-1]
        cs = s[:, :, -1]

        na = self.policy.choose_action(cs)
        (ns, p) = self.environment.next_state_sample(cs, na)
        nr = self.environment.reward(cs, na, ns)
        done = self.environment.is_terminal(ns)

        a = np.dstack([a, na])
        s = np.dstack([s, ns])
        r = np.dstack([r, nr])

        S[-1] = s
        A[-1] = a
        R[-1] = r

        t += 1
        ep_len += 1
    
    """
    s = self.environment.sample_states(N)
    S = [make3D(s[i, :, :], self.environment.sdim) for i in range(N)]
    A = [np.zeros((1, self.environment.adim, 0)) for i in range(N)]
    R = [np.zeros((1, 1, 0)) for i in range(N)]
    DONE = [False for i in range(N)]
    for i in range(self.params["episode_len"]):
      for j in range(N):
        if DONE[j] == False:
          s = S[j]
          a = A[j]
          r = R[j]
          cs = s[:, :, -1]

          na = self.policy.choose_action(cs)
          (ns, p) = self.environment.next_state_sample(cs, na)
          nr = self.environment.reward(cs, na, ns)

          is_done = self.environment.is_terminal(ns)
          if is_done == True:
            DONE[j] = True

          a = np.dstack([a, na])
          s = np.dstack([s, ns])
          r = np.dstack([r, nr])

          S[j] = s
          A[j] = a
          R[j] = r
    """

    # delete last state
    for j in range(len(S)):
      s = S[j]
      s = s[:, :, :-1]
      S[j] = s
    GT = [self._mc_gt(R[j]) for j in range(len(R))]

    for j in range(len(S)):
      assert S[j].shape[2] == A[j].shape[2]
      assert A[j].shape[2] == GT[j].shape[2]

    """
    print("Rendering a single episode")
    s = S[0].transpose((2, 1, 0))
    a = A[0].transpose((2, 1, 0))
    r = R[0].transpose((2, 1, 0))
    print(s.shape[0])
    for i in range(s.shape[0]):
      self.environment.render2(s[i, :, :])
      time.sleep(1.0 / 60.0)
    print("Done rendering a single episode")
    """


    s = np.vstack([s.transpose((2, 1, 0)) for s in S])
    a = np.vstack([a.transpose((2, 1, 0)) for a in A])
    gt = np.vstack([gt.transpose((2, 1, 0)) for gt in GT])
    episode_lens = np.array([GT[j].size for j in range(len(GT))])
    return (s, a, gt, episode_lens)

  def iterate(self):
    t1 = time.time()
    (s, a, gt, episode_lens) = self._episodes()
    t2 = time.time()
    print("Generating episodes took %f s" % (t2 - t1))
    episode_idx = np.hstack([[0], np.cumsum(episode_lens)[0:-1]])
    adv = gt

    if self.params["baseline"] == True:
      print("Training baseline")
      (s, layer_nb) = unstack2D(s)
      (gt, _) = unstack2D(gt)

      b = self.sess.run(self.b_, feed_dict={self.s_: s})
      train_till_convergence_or_for(self.sess, self.b_loss_, self.b_train_,
          [self.s_, self.b_target_], [s, gt], times=200)

      b = stack2D(b, layer_nb)
      s = stack2D(s, layer_nb)
      gt = stack2D(gt, layer_nb)
      adv = adv - b
    if self.params["normalize_adv"] == True:
      print("Normalizing advantage")
      adv -= np.mean(adv)
      adv /= np.std(adv)

    self.policy.train(s, a, adv, 1)
    idx = episode_idx[np.random.randint(len(episode_lens))]
    return (np.mean(gt[episode_idx]), np.mean(episode_lens))
###############################################################################
