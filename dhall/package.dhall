--| hostbootstrap project-config schema (Dhall).
--
-- A project's `hostbootstrap.dhall` imports this package and builds a typed
-- value. Each substrate picks exactly one execution model — `Container`,
-- `HostBinary`, or `HostDaemon` — expressed as a Dhall union. Because each
-- variant is a distinct record type, illegal states are unrepresentable at the
-- type level: only `HostDaemon` has a `daemon` field (and it is required), only
-- `Container` has `service`/`mounts`, only `HostBinary` has `handoff`.
--
-- `dhall-to-json` strips union tags, so `entry` lowers the union into a
-- self-describing record carrying an explicit `tag` plus one populated payload.
-- The hostbootstrap CLI reads that JSON.

let Flavor = < Cpu | Cuda >

let Mount = { host : Text, container : Text, ro : Bool }

let HostReqs = { ghc : Bool, tart : Bool, metal : Bool }

let Build = { cabal : Text, host : HostReqs }

let Handoff = { up : Text, down : Text, delete : Optional Text }

let CtrArtifact = { dockerfile : Text, flavor : Flavor }

let Container =
      { dockerfile : Text, flavor : Flavor, service : Bool, mounts : List Mount }

let HostBinary =
      { build : Build, container : Optional CtrArtifact, handoff : Handoff }

let HostDaemon = { build : Build, daemon : Text, container : Optional CtrArtifact }

let Model =
      < Container : Container | HostBinary : HostBinary | HostDaemon : HostDaemon >

let Substrate = < AppleSilicon | LinuxCpu | LinuxGpu >

let RModel =
      { tag : Text
      , container : Optional Container
      , hostBinary : Optional HostBinary
      , hostDaemon : Optional HostDaemon
      }

let REntry = { substrate : Text, model : RModel }

let Config = { project : Text, substrates : List REntry }

let renderModel
    : Model -> RModel
    = \(m : Model) ->
        merge
          { Container =
              \(c : Container) ->
                { tag = "Container"
                , container = Some c
                , hostBinary = None HostBinary
                , hostDaemon = None HostDaemon
                }
          , HostBinary =
              \(b : HostBinary) ->
                { tag = "HostBinary"
                , container = None Container
                , hostBinary = Some b
                , hostDaemon = None HostDaemon
                }
          , HostDaemon =
              \(d : HostDaemon) ->
                { tag = "HostDaemon"
                , container = None Container
                , hostBinary = None HostBinary
                , hostDaemon = Some d
                }
          }
          m

let renderSubstrate
    : Substrate -> Text
    = \(s : Substrate) ->
        merge
          { AppleSilicon = "apple-silicon"
          , LinuxCpu = "linux-cpu"
          , LinuxGpu = "linux-gpu"
          }
          s

let entry
    : Substrate -> Model -> REntry
    = \(s : Substrate) ->
      \(m : Model) ->
        { substrate = renderSubstrate s, model = renderModel m }

let config
    : Config -> Config
    = \(c : Config) -> c

in  { Flavor
    , Mount = { Type = Mount, default = { ro = False } }
    , HostReqs =
      { Type = HostReqs, default = { ghc = False, tart = False, metal = False } }
    , Build =
      { Type = Build
      , default = { host = { ghc = False, tart = False, metal = False } }
      }
    , Handoff = { Type = Handoff, default = { delete = None Text } }
    , CtrArtifact
    , Container =
      { Type = Container
      , default = { flavor = Flavor.Cpu, service = False, mounts = [] : List Mount }
      }
    , HostBinary = { Type = HostBinary, default = { container = None CtrArtifact } }
    , HostDaemon = { Type = HostDaemon, default = { container = None CtrArtifact } }
    , Model
    , Substrate
    , entry
    , config
    }
