"""Trains a model, saving checkpoints and tensorboard summaries along
   the way."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from numpy import genfromtxt

from datetime import datetime
import json
import os
import shutil
from timeit import default_timer as timer

import tensorflow.compat.v1 as tf
tf.disable_v2_behavior()
import numpy as np
import input_data
from NN_model import Model
import csv
import itertools


import argparse

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument("--batch_range", type=int, nargs='+', default=[64],
                            help="batch range")

parser.add_argument("--ratio_range", type=float, nargs='+', default=[0.7, 0.8],
                            help="ratio range")

parser.add_argument("--stable", type=int, default=1,
                            help="number of subsets")

parser.add_argument("--data_set", type=str, default="mnist",
                            help="number of subsets")

with open('config.json') as config_file:
    config = json.load(config_file)


args = parser.parse_args()
print(args)

# Setting up training parameters
tf.set_random_seed(config['random_seed'])
max_num_training_steps = config['max_num_training_steps']
num_output_steps = config['num_output_steps']
num_summary_steps = config['num_summary_steps']
num_checkpoint_steps = config['num_checkpoint_steps']
training_size = config['training_size']
data_set = args.data_set
batch_range = args.batch_range
ratio_range = args.ratio_range
stable = args.stable
initial_learning_rate = config['initial_learning_rate']
eta = config['constant_learning_rate']
learning_rate = tf.train.exponential_decay(initial_learning_rate, 0, 5, 0.85, staircase=True)

# Setting up the data and the model
if data_set == "mnist":
  data = input_data.load_mnist_data_set(validation_size= (60000 - training_size))
if data_set == "cifar":
  data = input_data.load_cifar_data_set(validation_size= (60000 - training_size))
global_step = tf.Variable(1, name="global_step")
num_features = data.train._images.shape[1]


for batch_size, subset_ratio in itertools.product(batch_range, ratio_range): #Parameters chosen with validation
  print(batch_size, subset_ratio)
  model = Model(subset_ratio, num_features)
  val_dict = {model.x_input: data.validation._images,
                  model.y_input: data.validation._labels}
  test_dict = {model.x_input: data.test._images,
                  model.y_input: data.test._labels}

  # Setting up the optimizer
  if stable:
      #CONSTANC STEP SIZE
      optimizer = tf.train.AdamOptimizer(eta).minimize(model.max_xent, global_step=global_step)
      #DECREASING STEP SIZE
      #optimizer = tf.train.AdamOptimizer(learning_rate).minimize(model.xent, global_step=global_step)

  else:
      var_list = [model.W1, model.b1, model.W3, model.b3]
      #CONSTANC STEP SIZE
      optimizer = tf.train.AdamOptimizer(eta).minimize(model.xent, global_step=global_step, var_list=var_list)
      #DECREASING STEP SIZE
      #optimizer = tf.train.AdamOptimizer(learning_rate).minimize(model.xent, global_step=global_step, var_list=var_list)

  avg_test_acc = 0
  test_accs = {}
  thetas = {}
  iterations = {}
  num_experiments = config['num_experiments']
  logits_acc = np.zeros((config['num_experiments'], 10000, 10))
  W1_acc = np.zeros((config['num_experiments'], 10000, 784*512))
  W2_acc = np.zeros((config['num_experiments'], 10000, 512*256))

  for experiment in range(num_experiments):
    print("Experiment", experiment)

    # Setting up the Tensorboard and checkpoint outputs
    model_dir = config['model_dir'] + str(datetime.now())
    if not os.path.exists(model_dir):
      os.makedirs(model_dir)

    with tf.Session() as sess:
      # Initialize the summary writer, global variables, and our time counter.
      #summary_writer = tf.summary.FileWriter(model_dir + "/Xent")
      #summary_writer1 = tf.summary.FileWriter(model_dir+ "/Max_Xent")
      #summary_writer2 = tf.summary.FileWriter(model_dir+ "/Accuracy")
      #summary_writer3 = tf.summary.FileWriter(model_dir+ "/Test_Accuracy")
      sess.run(tf.global_variables_initializer())
      training_time = 0.0

      # Main training loop
      best_val_acc = 0
      test_acc = 0
      num_iters = 0
      for ii in range(max_num_training_steps):
        x_batch, y_batch = data.train.next_batch(batch_size)

        nat_dict = {model.x_input: x_batch,
                    model.y_input: y_batch}

        # Output
        if ii % num_output_steps == 0:
          nat_acc = sess.run(model.accuracy, feed_dict=nat_dict)
          val_acc = sess.run(model.accuracy, feed_dict=val_dict)
          nat_xent = sess.run(model.xent, feed_dict=nat_dict)
          max_xent = sess.run(model.max_xent, feed_dict=nat_dict)
          print('Step {}:    ({})'.format(ii, datetime.now()))
          print('    training nat accuracy {:.4}'.format(nat_acc * 100))
          print('    validation nat accuracy {:.4}'.format(val_acc * 100))
          print('    Nat Xent {:.4}'.format(nat_xent))
          print('    Max Xent {:.4}'.format(max_xent))

          #Validation
          if val_acc > best_val_acc:
            best_val_acc = val_acc
            num_iters = ii
            test_acc = sess.run(model.accuracy, feed_dict=test_dict)

          #Tensorboard Summaries
          #summary = tf.Summary(value=[
          #    tf.Summary.Value(tag='Xent', simple_value= nat_xent),])
          #summary1 = tf.Summary(value=[
          #    tf.Summary.Value(tag='Xent', simple_value= max_xent),])
          #summary2 = tf.Summary(value=[
          #    tf.Summary.Value(tag='Accuracy', simple_value= nat_acc*100)])
          #summary3 = tf.Summary(value=[
          #    tf.Summary.Value(tag='Accuracy', simple_value= test_acc*100)])
          #summary_writer.add_summary(summary, global_step.eval(sess))
          #summary_writer1.add_summary(summary1, global_step.eval(sess))
          #summary_writer2.add_summary(summary2, global_step.eval(sess))
          #summary_writer3.add_summary(summary3, global_step.eval(sess))

          if ii != 0:
            print('    {} examples per second'.format(
                num_output_steps * batch_size / training_time))
            training_time = 0.0
        

        # Actual training step
        start = timer()
        sess.run(optimizer, feed_dict=nat_dict)
        end = timer()
        training_time += end - start


      #Output test results 
      theta= sess.run(model.theta, feed_dict=test_dict)
      test_accs[experiment] = test_acc  * 100
      thetas[experiment] = theta
      logits_acc[experiment] = sess.run(model.logits, feed_dict=test_dict)
      W1_acc[experiment] = sess.run(model.W1, feed_dict=test_dict).reshape(-1, 784*512)
      W2_acc[experiment] = sess.run(model.W2, feed_dict=test_dict).reshape(-1, 512*256)
      iterations[experiment] = num_iters
      avg_test_acc += test_acc

  avg_test_acc  = avg_test_acc/num_experiments
  print('  average testing accuracy {:.4}'.format(avg_test_acc  * 100))
  print('  Theta values', thetas)
  print('  individual accuracies: \n', test_accs)
  std = np.array([float(test_accs[k]) for k in test_accs]).std()
  print('  Standard deviation {:.2}'.format(np.array([float(test_accs[k]) for k in test_accs]).std()))
  print("Logits stability", np.mean(np.std(logits_acc, axis=0), axis=0))
  logit_stability =  np.mean(np.std(logits_acc, axis=0), axis=0)
  w1_stability = np.mean(np.std(W1_acc, axis=0), axis=0)
  w2_stability = np.mean(np.std(W2_acc, axis=0), axis=0)
  print("W1 stability", np.mean(np.std(W1_acc, axis=0), axis=0))
  print("W2 stability", np.mean(np.std(W2_acc, axis=0), axis=0))

  file = open(str('results' + data_set + '.csv'), 'a+', newline ='')
  with file:
    writer = csv.writer(file) 
    writer.writerow([stable, num_experiments, training_size, batch_size, subset_ratio, avg_test_acc, test_accs, std, thetas, max_num_training_steps, iterations, w1_stability, w2_stability, logit_stability])




