import numpy as np
import tensorflow as tf

import bayesflow as bf
import bayesflow.util as util


from bayesflow.models import ConditionalDistribution
from bayesflow.models.q_distributions import QDistribution


"""
The current story for deterministic dependencies and transformations is really ugly.
Defining a transformed variable requires first defining the original variable,
then creating a new dependent variable, then attaching a Q distribution 
to that dependent variable to pass through the values from the parent Q distribution. 

This basically works but it's a hack and I need to find a more elegant solution. 

"""

class DeterministicTransform(ConditionalDistribution):

    def __init__(self, A, **kwargs):
        super(DeterministicTransform, self).__init__(A=A, **kwargs)
        
    def inputs(self):
        return ("A")
        
    def _logp(self, result, A):
        return tf.constant(0.0, dtype=tf.float32)
        
    def _compute_dtype(self, A_dtype):
        return A_dtype

    def attach_q(self):
        raise Exception("cannot attach an explicit Q distribution to a deterministic transform. attach to the parent instead!")

    
class TransposeQDistribution(QDistribution):
    def __init__(self, parent_q):

        
        super(PointwiseTransformedQDistribution, self).__init__(shape=parent_q.output_shape)

        for param in self.params():
            self.__dict__[param] = tf.transpose(parent_q.__dict__[param])
        
    def sample_stochastic_inputs(self):
        return self.parent_q.sample_stochastic_inputs()
        
    def entropy(self):        
        return tf.constant(0.0, dtype=tf.float32)
            
class Transpose(DeterministicTransform):
    def __init__(self, A, **kwargs):
        super(Transpose, self).__init__(A=A, **kwargs)
        
    def _sample(self, A):
        return A.T
    
    def _compute_shape(self, A_shape):
        N, D = A_shape
        return (D, A)
        
    def __getattr__(self, name):
        # hack to generate the Q distribution when it's first requested. we can't do this at initialization
        # time since the parent might not have a Q distribution attached yet.
        
        if name=="q_distribution":
            parent_q = self.input_nodes["A"].q_distribution
            self.q_distribution = TransposeQDistribution(parent_q)
            return self.q_distribution

        raise AttributeError(name)


class PointwiseTransformedQDistribution(QDistribution):
    def __init__(self, parent_q, transform, implicit=False):

        super(PointwiseTransformedQDistribution, self).__init__(shape=parent_q.output_shape)
        self.sample, self.log_jacobian = transform(parent_q.sample)

        # an "implicit" transformation is a formal object associated with a deterministic
        # transformation in the model, where the parent q distribution is associated with
        # the untransformed variable. In this case the ELBO expectations are with respect
        # to the parent Q distribution, so the jacobian of the transformation does not appear.
        # By contrast, a non-implicit use of a transformed Q distribution would be to create
        # a new type of distribution (eg, lognormal by exponentiating a Gaussian parent)
        # that could then itself be associated with stochastic variables in the graph.
        self.implicit = implicit
        self.parent_q = parent_q
        
    def sample_stochastic_inputs(self):
        if self.implicit:
            return {}
        else:
            return self.parent_q.sample_stochastic_inputs()
        
    def entropy(self):
        if self.implicit:
            return tf.constant(0.0, dtype=tf.float32)
        else:
            return self.parent_q.entropy() + self.log_jacobian
        

    
class PointwiseTransformedMatrix(DeterministicTransform):

    def __init__(self, A, transform, **kwargs):
        self.transform=transform
        super(PointwiseTransformedMatrix, self).__init__(A=A, **kwargs)        
        
    def _compute_shape(self, A_shape):
        return A_shape

    def _sample(self, A):
        tA, _ = self.transform(A)
        return tA
    
    def attach_q(self):
        raise Exception("cannot attach an explicit Q distribution to a deterministic transform. attach to the parent instead!")

    def __getattr__(self, name):
        # hack to generate the Q distribution when it's first requested. we can't do this at initialization
        # time since the parent might not have a Q distribution attached yet.
        
        if name=="q_distribution":
            parent_q = self.input_nodes["A"].q_distribution
            self.q_distribution = PointwiseTransformedQDistribution(parent_q, self.transform, implicit=True)
            return self.q_distribution

        raise AttributeError(name)
                
