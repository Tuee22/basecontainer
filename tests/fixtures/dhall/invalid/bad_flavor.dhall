-- `Gpu` is not a constructor of the Flavor enum (<Cpu | Cuda>).
let H = ../../../../dhall/package.dhall

in  H.config
      { project = "demo"
      , substrates =
        [ H.entry
            H.Substrate.LinuxGpu
            (H.Model.Container H.Container::{ dockerfile = "d", flavor = H.Flavor.Gpu })
        ]
      }
