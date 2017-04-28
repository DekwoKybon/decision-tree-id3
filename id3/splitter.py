import numpy as np
from .utils import unique


class SplitRecord():
    LESS = 0
    GREATER = 1

    def __init__(self, calc_record, bag, value_encoded, value_decoded=None):
        self.calc_record = calc_record
        self.bag = bag
        self.value_encoded = value_encoded
        self.value_decoded = value_decoded
        self.size = len(bag) if bag is not None else 0


class CalcRecord():
    NUM = 0
    NOM = 1

    def __init__(self,
                 split_type,
                 info,
                 feature_idx=None,
                 feature_name=None,
                 entropy=None,
                 pivot=None,
                 attribute_counts=None,
                 class_counts=None):
        self.split_type = split_type
        self.info = info
        self.feature_idx = feature_idx
        self.feature_name = feature_name
        self.entropy = entropy
        self.pivot = pivot
        self.class_counts = class_counts
        self.attribute_counts = attribute_counts

    def __lt__(self, other):
        if not isinstance(other, CalcRecord):
            return True
        return self.info < other.info


class Splitter():

    def __init__(self, X, y, is_numerical, encoders, gain_ratio=False):
        self.X = X
        self.y = y
        self.is_numerical = is_numerical
        self.encoders = encoders
        self.gain_ratio = gain_ratio

    def _entropy(self, y, return_class_counts=False):
        """ Entropy for the classes in the array y
        :math: \sum_{x \in X} p(x) \log_{2}(1/p(x)) :math: from
        https://en.wikipedia.org/wiki/ID3_algorithm

        Parameters
        ----------
        y : nparray of shape [n remaining attributes]
            containing the class names

        Returns
        -------
        : float
            information for remaining examples given feature
        """
        n = y.shape[0]
        if n <= 0:
            return 0
        classes, count = unique(y)
        p = np.true_divide(count, n)
        res = np.sum(np.multiply(p, np.log2(np.reciprocal(p))))
        if return_class_counts:
            return res, np.vstack((classes, count)).T
        else:
            return res

    def _info_nominal(self, x, y):
        """ Info for nominal feature feature_values
        :math: p(a)H(a) :math: from
        https://en.wikipedia.org/wiki/ID3_algorithm

        Parameters
        ----------
        x : np.array of shape [n remaining examples]
            containing feature values
        y : np.array of shape [n remaining examples]
            containing relevent class

        Returns
        -------
        : float
            information for remaining examples given feature
        """
        info = 0
        n = x.shape[0]
        items, count = unique(x)
        for value, p in zip(items, count):
            info += p * self._entropy(y[x == value])
        return CalcRecord(CalcRecord.NOM,
                          info * np.true_divide(1, n),
                          attribute_counts=count)

    def _info_numerical(self, x, y):
        """ Info for numerical feature feature_values
        sort values then find the best split value

        Parameters
        ----------
        x : np.array of shape [n remaining examples]
            containing feature values
        y : np.array of shape [n remaining examples]
            containing relevent class

        Returns
        -------
        : float
            information for remaining examples given feature
        : float
            pivot used set1 < pivot <= set2
        """
        n = x.size
        """
        if np.max(x) == np.min(x):
#TODO
            return CalcRecord(CalcRecord.NOM,
                              self._entropy(y),
                              pivot=0.0,
                              attribute_counts=np.array([n]))
        """
        sorted_idx = np.argsort(x, kind='quicksort')
        sorted_y = np.take(y, sorted_idx, axis=0)
        sorted_x = np.take(x, sorted_idx, axis=0)
        min_info = float('inf')
        min_info_pivot = 0
        min_attribute_counts = np.empty(2)
        for i in range(1, n):
            if sorted_x[i - 1] != sorted_x[i]:
                tmp_info = (i) * self._entropy(sorted_y[0: i]) + \
                           (n - (i)) * self._entropy(sorted_y[i:])
                if tmp_info < min_info:
                    min_attribute_counts[SplitRecord.LESS] = n - i
                    min_attribute_counts[SplitRecord.GREATER] = i
                    min_info = tmp_info
                    min_info_pivot = sorted_x[i - 1]
        return CalcRecord(CalcRecord.NUM,
                          min_info * np.true_divide(1, n),
                          pivot=min_info_pivot,
                          attribute_counts=min_attribute_counts)

    def _split_nominal(self, X_, examples_idx, calc_record):
        ft_idx = calc_record.feature_idx
        values = self.encoders[ft_idx].encoded_classes_
        classes = self.encoders[ft_idx].classes_
        split_records = [None] * len(values)
        for val, i in enumerate(values):
            split_records[i] = SplitRecord(calc_record,
                                           examples_idx[X_[:, ft_idx] == val],
                                           val,
                                           classes[i])
        return split_records

    def _split_numerical(self, X_, examples_idx, calc_record):
        idx = calc_record.feature_idx
        split_records = [None] * 2
        split_records[0] = SplitRecord(calc_record,
                                       examples_idx[X_[:, idx]
                                                    <= calc_record.pivot],
                                       SplitRecord.LESS)
        split_records[1] = SplitRecord(calc_record,
                                       examples_idx[X_[:, idx]
                                                    > calc_record.pivot],
                                       SplitRecord.GREATER)
        return split_records

    def _gain_ratio(self, calc_record):
        """ Calculates the gain ratio using CalcRecord
        :math: - \sum_{i} \fraq{|S_i|}{|S|}\log_2 (\fraq{|S_i|}{|S|}):math:

        Parameters
        ----------
        calc_record : CalcRecord

        Returns
        -------
        : float
        """
        counts = calc_record.attribute_counts
        s = np.true_divide(counts, np.sum(counts))
        return - np.sum(np.multiply(s, np.log2(s)))

    def _is_less(self, calc_record1, calc_record2):
        """Compairs CalcRecords

        Parameters
        ----------
        calc_record1 : CalcRecord
        calc_record2 : CalcRecord

        Returns
        -------
        : bool
            if calc_record1 > calc_record2
        """
        if calc_record1 is None:
            return True
        if calc_record2 is None:
            return False
        if self.gain_ratio:
            gain_ratio1 = self._gain_ratio(calc_record1)
            gain_ratio2 = self._gain_ratio(calc_record2)
            return (np.true_divide(calc_record1.info, gain_ratio1)
                    > np.true_divide(calc_record2.info, gain_ratio2))
        else:
            return calc_record1.info > calc_record2.info

    def calc(self, examples_idx, features_idx):
        """ Calculates information regarding optimal split based on information
        gain

        Parameters
        ----------
        x : np.array of shape [n remaining examples]
            containing feature values
        y : np.array of shape [n remaining examples]
            containing relevent class

        Returns
        -------
        : float
            information for remaining examples given feature
        : float
            pivot used set1 < pivot <= set2
        """
        X_ = self.X[np.ix_(examples_idx, features_idx)]
        y_ = self.y[examples_idx]
        calc_record = None
        entropy, class_counts = self._entropy(y_, True)
        for idx, feature in enumerate(X_.T):
            tmp_calc_record = None
            if self.is_numerical[features_idx[idx]]:
                tmp_calc_record = self._info_numerical(feature, y_)
            else:
                tmp_calc_record = self._info_nominal(feature, y_)
            if self._is_less(calc_record, tmp_calc_record):
                calc_record = tmp_calc_record
                calc_record.feature_idx = features_idx[idx]
        calc_record.entropy, calc_record.class_counts = entropy, class_counts
        return calc_record

    def split(self, examples_idx, calc_record):
        X_ = self.X[np.ix_(examples_idx)]
        if self.is_numerical[calc_record.feature_idx]:
            return self._split_numerical(X_, examples_idx, calc_record)
        else:
            return self._split_nominal(X_, examples_idx, calc_record)
