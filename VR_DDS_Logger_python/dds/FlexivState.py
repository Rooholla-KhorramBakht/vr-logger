"""
  Generated by Eclipse Cyclone DDS idlc Python Backend
  Cyclone DDS IDL version: v0.10.5
  Module: 
  IDL file: quest_state.idl

"""

from enum import auto
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass

import cyclonedds.idl as idl
import cyclonedds.idl.annotations as annotate
import cyclonedds.idl.types as types


@dataclass
@annotate.final
@annotate.autoid("sequential")
class FlexivStateMsg(idl.IdlStruct, typename="FlexivState"):
    q: types.array[types.float32, 7]
    dq: types.array[types.float32, 7]
    tau: types.array[types.float32, 7]