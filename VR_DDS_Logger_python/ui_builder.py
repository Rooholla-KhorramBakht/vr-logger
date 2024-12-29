# Copyright (c) 2022-2024, NVIDIA CORPORATION. All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto. Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

import numpy as np
import omni.timeline
import omni.ui as ui
from omni.isaac.core.articulations import Articulation
from omni.isaac.core.objects.cuboid import FixedCuboid
from omni.isaac.core.prims import XFormPrim
from omni.isaac.core.utils.prims import is_prim_path_valid
from omni.isaac.core.utils.stage import add_reference_to_stage, create_new_stage, get_current_stage
from omni.isaac.core.world import World
from omni.isaac.nucleus import get_assets_root_path
from omni.isaac.ui.element_wrappers import CollapsableFrame, StateButton
from omni.isaac.ui.element_wrappers.core_connectors import LoadButton, ResetButton
from omni.isaac.ui.ui_utils import get_style
from omni.usd import StageEventType
from pxr import Sdf, UsdLux
from omni.usd import get_prim_at_path
from .dds.PoseMsg import VRPose

from .scenario import FlexivJointMimicScenario

from omni.isaac.core.utils.nucleus import get_assets_root_path
from omni.isaac.core.utils.stage import add_reference_to_stage
from omni.isaac.core.robots import Robot
from omni.isaac.core import World
import carb
import omni.isaac.core.utils.carb as carb_utils
from .scene import PCDManager
from .annotator import AnnotatorManager
import os
from omni.isaac.core.utils.numpy.rotations import euler_angles_to_quats, quats_to_rot_matrices, rot_matrices_to_quats
from .dds.telemetry import VRPosePublihser
from .dds.PoseMsg import VRPose

class UIBuilder:
    def __init__(self):
        # Frames are sub-windows that can contain multiple UI elements
        self.frames = []
        # UI elements created using a UIElementWrapper instance
        self.wrapped_ui_elements = []

        # Get access to the timeline to control stop/pause/play programmatically
        self.dds_enable = True
        self._timeline = omni.timeline.get_timeline_interface()
        try:
            self.vr_pose_publihser = VRPosePublihser('vr_poses_msg')
        except:
            print('Could not initialize the DDS. Make sure the network settings is right.')
            self.dds_enable = False

        self._on_init()
    
    def get_vr_state(self):
        try:
            return dict(
            hmd_q = self.hmd_q, 
            left_q = self.left_q,
            right_q = self.right_q,
            hmd_t = self.hmd_t,
            left_t = self.left_t,
            right_t = self.right_t,
            )
        except:
            return None
    ###################################################################################
    #           The Functions Below Are Called Automatically By extension.py
    ###################################################################################

    def on_menu_callback(self):
        """Callback for when the UI is opened from the toolbar.
        This is called directly after build_ui().
        """
        pass

    def on_timeline_event(self, event):
        """Callback for Timeline events (Play, Pause, Stop)

        Args:
            event (omni.timeline.TimelineEventType): Event Type
        """
        if event.type == int(omni.timeline.TimelineEventType.STOP):
            # When the user hits the stop button through the UI, they will inevitably discover edge cases where things break
            # For complete robustness, the user should resolve those edge cases here
            # In general, for extensions based off this template, there is no value to having the user click the play/stop
            # button instead of using the Load/Reset/Run buttons provided.
            self._scenario_state_btn.reset()
            self._scenario_state_btn.enabled = False

    def extractPrimPose(self, prim_path):
        if is_prim_path_valid(prim_path):
            hmd_prim = get_prim_at_path(prim_path)
            T = hmd_prim.GetProperty('xformOp:transform').Get()
            q = T.ExtractRotationQuat()
            q = np.hstack([np.array(q.GetImaginary()), q.GetReal()])
            t = np.array(T.ExtractTranslation())
            return np.array(T).T, t, q
        else:
            return None, None, None
 
    def on_physics_step(self, step: float):
        """Callback for Physics Step.
        Physics steps only occur when the timeline is playing

        Args:
            step (float): Size of physics step
        """
        hmd_prim_path = '/_xr_gui/vr/_coord/xrdevice/xrdisplaydevice0'
        right_controller_prim_path = '/_xr_gui/vr/_coord/xrdevice/xrcontroller1'
        left_controller_prim_path = '/_xr_gui/vr/_coord/xrdevice/xrcontroller0'
        vr_T_hmd, hmd_t, hmd_q = self.extractPrimPose(hmd_prim_path)
        vr_T_left, left_t, left_q = self.extractPrimPose(left_controller_prim_path)
        vr_T_right, right_t, right_q = self.extractPrimPose(right_controller_prim_path)
        world_T_vr = np.eye(4)
        world_T_vr[:3, :3] = quats_to_rot_matrices(euler_angles_to_quats([np.pi/2,0, 0]))
        
        if vr_T_hmd is not None:
            world_T_right = world_T_vr@vr_T_right
            world_T_left = world_T_vr@vr_T_left
            world_T_hmd = world_T_vr@vr_T_hmd

            hmd_q = rot_matrices_to_quats(world_T_hmd[:3,:3])
            left_q = rot_matrices_to_quats(world_T_left[:3,:3])
            right_q = rot_matrices_to_quats(world_T_right[:3,:3])
            hmd_t = world_T_hmd[:3,-1]
            left_t = world_T_left[:3,-1]
            right_t = world_T_right[:3,-1]
            if self.dds_enable:
                vr_msg = VRPose(
                    hmd_q = hmd_q.tolist(), 
                    hmd_t = hmd_t.tolist(), 
                    left_q = left_q.tolist(), 
                    left_t = left_t.tolist(), 
                    right_q = right_q.tolist(), 
                    right_t = right_t.tolist()
                )
                self.vr_pose_publihser.send(vr_msg)
            self.hmd_q = hmd_q
            self.left_q = left_q
            self.right_q = right_q
            self.hmd_t = hmd_t
            self.left_t = left_t
            self.right_t = right_t


        # self.front_cam_img = self.annotation_manager.getData('front_cam:rgb')

    def on_stage_event(self, event):
        """Callback for Stage Events

        Args:
            event (omni.usd.StageEventType): Event Type
        """
        if event.type == int(StageEventType.OPENED):
            # If the user opens a new stage, the extension should completely reset
            self._reset_extension()

    def cleanup(self):
        """
        Called when the stage is closed or the extension is hot reloaded.
        Perform any necessary cleanup such as removing active callback functions
        Buttons imported from omni.isaac.ui.element_wrappers implement a cleanup function that should be called
        """
        for ui_elem in self.wrapped_ui_elements:
            ui_elem.cleanup()

    def build_ui(self):
        """
        Build a custom UI tool to run your extension.
        This function will be called any time the UI window is closed and reopened.
        """
        world_controls_frame = CollapsableFrame("World Controls", collapsed=False)

        with world_controls_frame:
            with ui.VStack(style=get_style(), spacing=5, height=0):
                self._load_btn = LoadButton(
                    "Load Button", "LOAD", setup_scene_fn=self._setup_scene, setup_post_load_fn=self._setup_scenario
                )

                self._load_btn.set_world_settings(physics_dt=1 / 60.0, rendering_dt=1 / 30.0)
                self.wrapped_ui_elements.append(self._load_btn)

                self._reset_btn = ResetButton(
                    "Reset Button", "RESET", pre_reset_fn=None, post_reset_fn=self._on_post_reset_btn
                )
                self._reset_btn.enabled = False
                self.wrapped_ui_elements.append(self._reset_btn)

        run_scenario_frame = CollapsableFrame("Run Scenario")

        with run_scenario_frame:
            with ui.VStack(style=get_style(), spacing=5, height=0):
                self._scenario_state_btn = StateButton(
                    "Run Scenario",
                    "RUN",
                    "STOP",
                    on_a_click_fn=self._on_run_scenario_a_text,
                    on_b_click_fn=self._on_run_scenario_b_text,
                    physics_callback_fn=self._update_scenario,
                )
                self._scenario_state_btn.enabled = False
                self.wrapped_ui_elements.append(self._scenario_state_btn)

    ######################################################################################
    # Functions Below This Point Support The Provided Example And Can Be Deleted/Replaced
    ######################################################################################

    def _on_init(self):
        self._articulation = None
        self._cuboid = None
        self._scenario = FlexivJointMimicScenario()

    def _add_light_to_stage(self):
        """
        A new stage does not have a light by default.  This function creates a spherical light
        """
        pass
        # sphereLight = UsdLux.SphereLight.Define(get_current_stage(), Sdf.Path("/World/SphereLight"))
        # sphereLight.CreateRadiusAttr(2)
        # sphereLight.CreateIntensityAttr(100000)
        # XFormPrim(str(sphereLight.GetPath())).set_world_pose([6.5, 0, 12])

    def _setup_scene(self):
        """
        This function is attached to the Load Button as the setup_scene_fn callback.
        On pressing the Load Button, a new instance of World() is created and then this function is called.
        The user should now load their assets onto the stage and add them to the World Scene.

        In this example, a new stage is loaded explicitly, and all assets are reloaded.
        If the user is relying on hot-reloading and does not want to reload assets every time,
        they may perform a check here to see if their desired assets are already on the stage,
        and avoid loading anything if they are.  In this case, the user would still need to add
        their assets to the World (which has low overhead).  See commented code section in this function.
        """
        if not is_prim_path_valid('/World/flexiv_rizon10s_kinematics'):
            asset_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),'assets/table-scene.usd') 
            add_reference_to_stage(usd_path=asset_path, prim_path="/World")
            settings = carb.settings.get_settings()
            # Set the VR anchor to our custom anchor
            carb_utils.set_carb_setting(settings, "/xrstage/profile/vr/anchorMode", "custom anchor")
            carb_utils.set_carb_setting(settings, 'xrstage/profile/vr/customAnchor', '/World/vr_anchor')
            # create a robot class to interact with the robot
            self._articulation = Articulation("/World/flexiv_rizon10s_kinematics")
            world = World.instance()
            world.scene.add(self._articulation)
            # Create a cuboid
            # self._cuboid = FixedCuboid(
            #     "/Scenario/cuboid", position=np.array([10.5, 0.0, 0.7]), size=0.05, color=np.array([255, 0, 0])
            # )
            # world.scene.add(self._cuboid)
            self._t_tool = Articulation('/World/t_tool/t_tool_obj')

            self.annotation_manager = AnnotatorManager(world)
            self.annotation_manager.registerCamera('/World/front_cam', 'front_cam', [1.2, 0, 0.7], [-0.66233, -0.66233, 0.24763, 0.24763], (320, 240))
            self.annotation_manager.setFocalLength('front_cam',24)
            self.annotation_manager.setClippingRange('front_cam', 0.1, 100)
            self.annotation_manager.registerAnnotator('front_cam', 'rgb')

    def _setup_scenario(self):
        """
        This function is attached to the Load Button as the setup_post_load_fn callback.
        The user may assume that their assets have been loaded by their setup_scene_fn callback, that
        their objects are properly initialized, and that the timeline is paused on timestep 0.

        In this example, a scenario is initialized which will move each robot joint one at a time in a loop while moving the
        provided prim in a circle around the robot.
        """
        self._reset_scenario()

        # UI management
        self._scenario_state_btn.reset()
        self._scenario_state_btn.enabled = True
        self._reset_btn.enabled = True

    def _reset_scenario(self):
        self._scenario.teardown_scenario()
        self._scenario.setup_scenario(self._articulation, self._t_tool, self.get_vr_state)
        pass

    def _on_post_reset_btn(self):
        """
        This function is attached to the Reset Button as the post_reset_fn callback.
        The user may assume that their objects are properly initialized, and that the timeline is paused on timestep 0.

        They may also assume that objects that were added to the World.Scene have been moved to their default positions.
        I.e. the cube prim will move back to the position it was in when it was created in self._setup_scene().
        """
        self._reset_scenario()

        # UI management
        self._scenario_state_btn.reset()
        self._scenario_state_btn.enabled = True

    def _update_scenario(self, step: float):
        """This function is attached to the Run Scenario StateButton.
        This function was passed in as the physics_callback_fn argument.
        This means that when the a_text "RUN" is pressed, a subscription is made to call this function on every physics step.
        When the b_text "STOP" is pressed, the physics callback is removed.

        Args:
            step (float): The dt of the current physics step
        """
        self._scenario.update_scenario(step)

    def _on_run_scenario_a_text(self):
        """
        This function is attached to the Run Scenario StateButton.
        This function was passed in as the on_a_click_fn argument.
        It is called when the StateButton is clicked while saying a_text "RUN".

        This function simply plays the timeline, which means that physics steps will start happening.  After the world is loaded or reset,
        the timeline is paused, which means that no physics steps will occur until the user makes it play either programmatically or
        through the left-hand UI toolbar.
        """
        self._timeline.play()

    def _on_run_scenario_b_text(self):
        """
        This function is attached to the Run Scenario StateButton.
        This function was passed in as the on_b_click_fn argument.
        It is called when the StateButton is clicked while saying a_text "STOP"

        Pausing the timeline on b_text is not strictly necessary for this example to run.
        Clicking "STOP" will cancel the physics subscription that updates the scenario, which means that
        the robot will stop getting new commands and the cube will stop updating without needing to
        pause at all.  The reason that the timeline is paused here is to prevent the robot being carried
        forward by momentum for a few frames after the physics subscription is canceled.  Pausing here makes
        this example prettier, but if curious, the user should observe what happens when this line is removed.
        """
        self._timeline.pause()

    def _reset_extension(self):
        """This is called when the user opens a new stage from self.on_stage_event().
        All state should be reset.
        """
        self._on_init()
        self._reset_ui()

    def _reset_ui(self):
        self._scenario_state_btn.reset()
        self._scenario_state_btn.enabled = False
        self._reset_btn.enabled = False
