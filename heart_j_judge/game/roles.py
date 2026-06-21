from enum import Enum


class Role(str, Enum):
    HEART_J = "heart_j"
    TRAITOR = "traitor"
    PRISONER = "prisoner"


class ControllerType(str, Enum):
    HUMAN = "human"
    AI = "ai"
    MOCK = "mock"
