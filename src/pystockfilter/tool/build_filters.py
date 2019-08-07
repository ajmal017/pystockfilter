# -*- coding: utf-8 -*-
""" pystockfilter

  Copyright 2019 Slash Gordon

  Use of this source code is governed by an MIT-style license that
  can be found in the LICENSE file.
"""
import datetime
import json
import logging

from pony.orm import commit, db_session
from pystockdb.db.schema.stocks import (Argument, Item, Price, Result, Signal,
                                        Stock, Symbol, Tag, Type)

from pystockfilter.base.base_helper import BaseHelper
from pystockfilter.filter.base_filter import BaseFilter


class BuildFilters:
    """
    This tool builds all filters
    """

    def __init__(self, arguments: dict, logger: logging.Logger):
        self.symbols = None
        self.filters = None
        if 'filters' in arguments:
            self.filters = arguments['filters']
        if 'symbols' in arguments:
            self.symbols = arguments['symbols']
        self.logger = logger

    def set_filters(self, filters):
        """
        Overwrite actual filter list
        :param filters: list with filters
        :return: nothing
        """
        self.filters = filters

    @db_session
    def build(self):
        """
        Starts the build process for given filters
        :return: nothing
        """
        if self.symbols is None or self.filters is None:
            return 1
        rc = 0
        for symbol_str in self.symbols:
            self.logger.info('Create filter for {}.'.format(symbol_str))
            # get stock of symbol
            stock = Stock.select(
                (lambda s: symbol_str in s.price_item.symbols.name)
            ).first()
            symbol = Symbol.get(name=symbol_str)
            for my_filter in self.filters:
                try:
                    self.logger.info(
                        'Execute filter {}.'.format(my_filter.name)
                    )
                    self.__build(my_filter, stock, symbol)
                except TypeError:
                    self.logger.exception(
                        'Filter {} causes exceptions.'.format(my_filter.name)
                        )
                    rc += 1
                except RuntimeError:
                    self.logger.exception(
                        'Filter {} causes exceptions.'.format(my_filter.name)
                        )
        commit()
        return rc

    def __build(self, my_filter, stock, symbol):
        if my_filter.look_back_date():

            bars = Price.select(
                lambda p: p.symbol.name == symbol.name
                and p.date >= my_filter.look_back_date()
                and p.date <= datetime.datetime.now()
                )
            my_filter.set_stock(stock)
            my_filter.set_bars(bars)
            strategy_status = my_filter.analyse()
            strategy_value = my_filter.get_calculation()
            tz = BaseHelper.get_timezone()
            fil_typ = Type.get(name='filter') or Type(name='filter')

            fil_tag = Tag.select(lambda t: t.name == my_filter.name and
                                 t.type.name == 'filter') or \
                Tag(name=my_filter.name, type=fil_typ)

            my_res = Result(
                value=strategy_value,
                status=strategy_status,
                date=datetime.datetime.now(tz)
            )
            # add arguments to result
            arg_typ = Type.get(name='argument') or Type(name='argument')

            for arg in my_filter.args:
                arg_tag = Tag.select(lambda t: t.name == arg and
                                     t.type.name == 'argument') or \
                                     Tag(name=my_filter.name, type=arg_typ)
                item = Item()
                item.add_tags([arg_tag])
                arg_str = json.dump(my_filter.args[arg])
                arg_obj = Argument(item=item, arg=arg_str)
                my_res.arguments.add(arg_obj)
            # create signal item
            sig_item = Item()
            sig_item.add_tags([fil_tag])
            my_sig = Signal(item=sig_item, result=my_res)
            # add stock to signal
            my_sig.price_items.add(symbol.price_item)
            if strategy_status == BaseFilter.BUY:
                self.logger.debug("Buy %s", symbol)
            elif strategy_status == BaseFilter.HOLD:
                self.logger.debug("Hold %s", symbol)
            else:
                self.logger.debug("Do not buy Stock %s ", symbol)
