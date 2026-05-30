let H = ../../../../dhall/package.dhall

in  H.config
      { project = "demo"
      , substrates =
        [ H.entry
            H.Substrate.LinuxCpu
            ( H.Model.Container
                H.Container::{
                , dockerfile = "docker/demo.Dockerfile"
                , service = True
                , mounts =
                  [ H.Mount::{ host = "./.data", container = "/opt/demo/.data" }
                  , H.Mount::{
                    , host = "/var/run/docker.sock"
                    , container = "/var/run/docker.sock"
                    }
                  ]
                }
            )
        ]
      }
